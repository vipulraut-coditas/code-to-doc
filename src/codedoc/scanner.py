"""Repository scanner — plain Python, no LLM.

Walks the repo, skips noise and secrets, detects the tech stack, scores each
file by how much it tells a Business Analyst, and keeps the top N files.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import pathspec

IGNORED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "bower_components", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "dist", "build",
    "target", "bin", "obj", "out", ".next", ".nuxt", ".svelte-kit", "coverage", ".idea",
    ".vscode", "vendor", "site-packages", ".gradle", ".terraform", ".dart_tool", "Pods",
}

# Never send these to an LLM.
SECRET_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "id_rsa*", "id_ed25519*",
    "*secret*", "*credential*", ".npmrc", ".pypirc", "*.tfstate", "*.tfvars",
]
SECRET_ALLOW = {".env.example", ".env.sample", ".env.template"}

SKIP_PATTERNS = [
    "*.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock",
    "*.min.js", "*.min.css", "*.map", "*.snap", "*.svg",
]

CODE_LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".mjs": "JavaScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".rs": "Rust", ".swift": "Swift",
    ".scala": "Scala", ".dart": "Dart", ".vue": "Vue", ".svelte": "Svelte", ".c": "C",
    ".cpp": "C++", ".h": "C/C++", ".sql": "SQL", ".graphql": "GraphQL", ".gql": "GraphQL",
    ".proto": "Protobuf", ".prisma": "Prisma",
}
DOC_CONFIG_EXT = {".md": "Markdown", ".rst": "reStructuredText", ".yaml": "YAML",
                  ".yml": "YAML", ".toml": "TOML", ".json": "JSON", ".xml": "XML",
                  ".ini": "INI", ".cfg": "INI", ".tf": "Terraform"}
SPECIAL_FILES = {"Dockerfile": "Docker", "Makefile": "Make", "Procfile": "Procfile",
                 "docker-compose.yml": "Docker", "docker-compose.yaml": "Docker"}

ENTRYPOINT_NAMES = {"main", "app", "server", "index", "manage", "wsgi", "asgi", "program", "application"}
HIGH_VALUE_DIRS = {
    "routes": 40, "router": 40, "routers": 40, "api": 40, "apis": 40, "controllers": 40,
    "controller": 40, "views": 35, "endpoints": 40, "handlers": 35, "resolvers": 35,
    "models": 40, "model": 40, "entities": 40, "entity": 40, "schemas": 35, "domain": 40,
    "services": 35, "service": 35, "usecases": 35, "use_cases": 35, "features": 30,
    "pages": 25, "screens": 25, "components": 10, "config": 10, "settings": 10,
}
LOW_VALUE_DIRS = {"tests": -40, "test": -40, "__tests__": -40, "spec": -35, "migrations": -20,
                  "fixtures": -30, "mocks": -30, "examples": -15, "scripts": -10, "static": -30,
                  "assets": -30, "public": -20, "locale": -30, "i18n": -30}

GROUPING_ROOTS = {"src", "app", "apps", "lib", "libs", "packages", "modules", "services", "internal", "pkg"}


@dataclass
class ScanResult:
    files: list[dict] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)
    readme: str = ""
    total_candidates: int = 0
    skipped_secrets: int = 0


def _matches(name: str, patterns: list[str]) -> bool:
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, p) for p in patterns)


def _is_secret(name: str) -> bool:
    return name.lower() not in SECRET_ALLOW and _matches(name, SECRET_PATTERNS)


def _language(path: Path) -> str | None:
    if path.name in SPECIAL_FILES:
        return SPECIAL_FILES[path.name]
    suffix = path.suffix.lower()
    return CODE_LANGUAGES.get(suffix) or DOC_CONFIG_EXT.get(suffix)


def module_of(rel: PurePosixPath) -> str:
    parts = rel.parts[:-1]
    if not parts:
        return "(root)"
    if parts[0].lower() in GROUPING_ROOTS and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    return parts[0]


def score(rel: PurePosixPath, language: str) -> int:
    name = rel.name.lower()
    stem = rel.stem.lower()
    points = 50 if language in CODE_LANGUAGES.values() else 0
    if stem == "readme":
        points += 120
    elif rel.suffix.lower() in {".md", ".rst"}:
        points += 15 if "docs" in [p.lower() for p in rel.parts] else 5
    if stem in ENTRYPOINT_NAMES:
        points += 40
    if name in {"package.json", "pyproject.toml", "requirements.txt", "pom.xml", "go.mod",
                "build.gradle", "composer.json", "gemfile", "cargo.toml", "openapi.yaml",
                "openapi.json", "swagger.yaml", "swagger.json", "schema.prisma"}:
        points += 45
    for part in rel.parts[:-1]:
        points += HIGH_VALUE_DIRS.get(part.lower(), 0) + LOW_VALUE_DIRS.get(part.lower(), 0)
    for keyword, bonus in (("model", 15), ("route", 15), ("controller", 15), ("service", 10),
                           ("schema", 10), ("api", 10), ("test", -40), ("spec", -25)):
        if keyword in stem:
            points += bonus
    if language in {"JSON", "YAML", "XML", "INI"} and points < 40:
        points -= 20
    return points - len(rel.parts)  # shallower files first on ties


def detect_stack(root: Path) -> list[str]:
    stack: list[str] = []

    def read(name: str) -> str:
        p = root / name
        try:
            return p.read_text(encoding="utf-8", errors="replace").lower() if p.is_file() else ""
        except OSError:
            return ""

    py = read("requirements.txt") + read("pyproject.toml") + read("setup.py") + read("Pipfile")
    if py:
        stack.append("Python")
        for lib, label in (("django", "Django"), ("fastapi", "FastAPI"), ("flask", "Flask"),
                           ("sqlalchemy", "SQLAlchemy"), ("celery", "Celery"),
                           ("langchain", "LangChain"), ("langgraph", "LangGraph"),
                           ("pydantic", "Pydantic"), ("streamlit", "Streamlit")):
            if lib in py:
                stack.append(label)

    pkg = read("package.json")
    if pkg:
        try:
            data = json.loads(pkg)
            deps = {**data.get("dependencies", {}), **data.get("devdependencies", {})}
        except json.JSONDecodeError:
            deps = {}
        stack.append("TypeScript" if "typescript" in deps or (root / "tsconfig.json").exists() else "JavaScript/Node.js")
        for lib, label in (("react", "React"), ("next", "Next.js"), ("vue", "Vue"),
                           ("@angular/core", "Angular"), ("svelte", "Svelte"),
                           ("express", "Express"), ("@nestjs/core", "NestJS"),
                           ("prisma", "Prisma"), ("mongoose", "MongoDB/Mongoose"),
                           ("typeorm", "TypeORM"), ("react-native", "React Native")):
            if lib in deps:
                stack.append(label)

    markers = {"pom.xml": "Java (Maven)", "build.gradle": "Java/Kotlin (Gradle)",
               "build.gradle.kts": "Kotlin (Gradle)", "go.mod": "Go", "Gemfile": "Ruby",
               "composer.json": "PHP", "Cargo.toml": "Rust", "pubspec.yaml": "Dart/Flutter",
               "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose"}
    for marker, label in markers.items():
        if (root / marker).exists():
            stack.append(label)
    if "spring" in read("pom.xml") + read("build.gradle"):
        stack.append("Spring")
    if any(root.glob("*.csproj")) or any(root.glob("*.sln")):
        stack.append(".NET")
    return list(dict.fromkeys(stack))


def _load_gitignore(root: Path) -> pathspec.GitIgnoreSpec | None:
    gi = root / ".gitignore"
    if not gi.is_file():
        return None
    try:
        lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    return pathspec.GitIgnoreSpec.from_lines(lines)


def _looks_binary(raw: bytes) -> bool:
    return b"\x00" in raw[:4096]


def scan_repository(root: str | Path, *, max_files: int = 300, max_file_bytes: int = 200_000,
                    max_chars_per_file: int = 12_000) -> ScanResult:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository folder not found: {root}")

    ignore = _load_gitignore(root)
    result = ScanResult(stack=detect_stack(root))
    candidates: list[tuple[int, PurePosixPath, Path, str]] = []

    stack_dirs = [root]
    while stack_dirs:
        current = stack_dirs.pop()
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            rel = PurePosixPath(entry.relative_to(root).as_posix())
            if entry.is_symlink():
                continue
            if entry.is_dir():
                if entry.name in IGNORED_DIRS or entry.name.startswith(".") and entry.name not in {".github"}:
                    continue
                if ignore and ignore.match_file(str(rel) + "/"):
                    continue
                stack_dirs.append(entry)
                continue
            if _is_secret(entry.name):
                result.skipped_secrets += 1
                continue
            if _matches(entry.name, SKIP_PATTERNS):
                continue
            if ignore and ignore.match_file(str(rel)):
                continue
            language = _language(entry)
            if not language:
                continue
            try:
                if entry.stat().st_size > max_file_bytes or entry.stat().st_size == 0:
                    continue
            except OSError:
                continue
            candidates.append((score(rel, language), rel, entry, language))

    result.total_candidates = len(candidates)
    candidates.sort(key=lambda c: (-c[0], str(c[1])))

    for points, rel, path, language in candidates:
        if len(result.files) >= max_files:
            break
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if _looks_binary(raw):
            continue
        text = raw.decode("utf-8", errors="replace")
        if rel.stem.lower() == "readme" and len(rel.parts) == 1 and not result.readme:
            result.readme = text[:8000]
        truncated = len(text) > max_chars_per_file
        result.files.append({
            "path": str(rel),
            "module": module_of(rel),
            "language": language,
            "priority": points,
            "content": text[:max_chars_per_file],
            "truncated": truncated,
        })
    return result
