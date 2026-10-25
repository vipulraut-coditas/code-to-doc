"""Interactive questions shown when a user runs ``codedoc``.

Flow:
  1. Which document(s) should be generated?         (one, all, or several via a checkbox)
  2. Which format(s)?                               (Markdown, Word, Google Docs -> Google sign-in)
  3. Which project should be documented?            (folder or git URL)
  4. API key or the installed Claude Code?           (Claude Code is verified)
  5. Which LLM provider?                             (API path only)
  6. API key                                         (hidden input)
  7. Fast model name / Smart model name
  8. Connection test
  9. Output folder for the documents                (skipped for Google Docs only)
 10. Save settings for next time?
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import questionary
from questionary import Choice
from rich.console import Console
from rich.table import Table

from codedoc.config import BACKEND_API, BACKEND_CLAUDE_CODE, Settings, config_file, save_settings
from codedoc.doctypes import DOC_TYPES, get_doc_type, parse_doc_types
from codedoc.formats import (FORMATS, GOOGLE_PACKAGE, GOOGLE_SETUP_HELP, get_format, google_authorize,
                             google_credentials_file, google_libraries_installed, google_token_file, parse_formats)
from codedoc.llm import build_llm, ping
from codedoc.llm_claude_cli import check_claude_code
from codedoc.providers import PROVIDERS, get_provider, install_package, is_installed, pip_install
from codedoc.repo_source import is_remote

console = Console()

CLAUDE_INSTALL_HELP = (
    "Install Claude Code, then run [bold]claude[/] once in a terminal and log in.\n"
    "Docs: https://docs.claude.com/en/docs/claude-code/overview"
)


# ---------------------------------------------------------------- helpers
def _not_empty(value: str) -> bool | str:
    return True if value.strip() else "This value is required"


def _repo_validator(value: str) -> bool | str:
    value = value.strip().strip('"')
    if not value:
        return "Please enter a folder path or a git URL"
    if is_remote(value) or Path(value).expanduser().is_dir():
        return True
    return "Folder not found"


def settings_table(settings: Settings, repo: str | None = None, output: Path | None = None,
                   doc_types: list[str] | None = None, formats: list[str] | None = None) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    if doc_types:
        table.add_row("Documents", "\n".join(get_doc_type(d).label for d in doc_types))
    if formats:
        table.add_row("Formats", ", ".join(get_format(f).label for f in formats))
    if repo:
        table.add_row("Project", repo)
    if settings.backend == BACKEND_CLAUDE_CODE:
        table.add_row("LLM", "Claude Code (installed CLI, no API key)")
    else:
        provider = get_provider(settings.provider)
        table.add_row("LLM", provider.label)
        if settings.base_url:
            table.add_row("Base URL", settings.base_url)
    table.add_row("Fast model", settings.fast_model)
    table.add_row("Smart model", settings.smart_model)
    if output:
        table.add_row("Output folder", str(output))
    return table


# ---------------------------------------------------------------- questions
def _ask_one_or_more(question: str, items: list, noun: str) -> str | list[str]:
    """Arrow + Enter picks exactly the highlighted item; several items need an explicit checkbox.

    ``items`` have ``id``, ``label`` and ``description``. Returns an id, ``"all"`` or a list of ids.
    """
    choices = [Choice(f"{x.label}  -  {x.description}", value=x.id) for x in items]
    choice = questionary.select(
        question,
        choices=choices + [Choice(f"All {noun}s", value="all"),
                           Choice(f"Several {noun}s (choose with a checkbox) ...", value="several")],
    ).unsafe_ask()
    if choice == "several":
        choice = questionary.checkbox(
            f"Which {noun}s?", choices=choices,
            instruction="(Space = tick/untick, Enter = confirm)",
            validate=lambda picked: True if picked else f"Tick at least one {noun} with Space",
        ).unsafe_ask()
    return choice


def ask_doc_types() -> list[str]:
    doc_types = parse_doc_types(_ask_one_or_more("Which document do you want to generate?", DOC_TYPES, "document"))
    console.print("[green]v[/] Will generate: " + ", ".join(get_doc_type(d).label for d in doc_types))
    return doc_types


def ask_formats() -> list[str]:
    formats = parse_formats(_ask_one_or_more("In which format should the documents be created?", FORMATS, "format"))
    if "gdoc" in formats and not ensure_google_ready():
        formats = [f for f in formats if f != "gdoc"] or ["md"]
        console.print("[yellow]![/] Skipping Google Docs.")
    console.print("[green]v[/] Format: " + ", ".join(get_format(f).label for f in formats))
    return formats


def ensure_google_ready() -> bool:
    """Install the Google library if needed, find the OAuth client file and sign in now (before the long run)."""
    if not google_libraries_installed():
        console.print(f"[yellow]![/] Google Docs output needs the Python package [bold]{GOOGLE_PACKAGE}[/].")
        if not questionary.confirm(f"Install {GOOGLE_PACKAGE} now with pip?", default=True).unsafe_ask():
            return False
        if not pip_install(GOOGLE_PACKAGE) or not google_libraries_installed():
            console.print(f"[red]x Installation failed.[/] Try: pip install {GOOGLE_PACKAGE}")
            return False
        console.print(f"[green]v[/] Installed {GOOGLE_PACKAGE}")

    client = google_credentials_file()
    if not client.exists() and not google_token_file().exists():
        console.print(GOOGLE_SETUP_HELP.format(path=client))
        answer = questionary.text("Path to the downloaded OAuth client JSON (leave empty to skip Google Docs):"
                                  ).unsafe_ask().strip().strip('"')
        if not answer:
            return False
        source = Path(answer).expanduser()
        if not source.is_file():
            console.print(f"[red]x File not found:[/] {source}")
            return False
        client.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, client)
        console.print(f"[green]v[/] Saved the OAuth client to {client}")

    try:
        with console.status("Signing in to Google (a browser window may open) ..."):
            google_authorize()
    except Exception as exc:
        console.print(f"[red]x Google sign-in failed:[/] {str(exc)[:600]}")
        return False
    console.print("[green]v[/] Signed in to Google.")
    return True


def ask_repo(default: str = "") -> str:
    answer = questionary.text(
        "Which project should I document? (folder path or git URL)",
        default=default, validate=_repo_validator,  # empty by default: no "." to delete before typing
    ).unsafe_ask()
    answer = answer.strip().strip('"')  # Windows "Copy as path" adds quotes
    return answer if is_remote(answer) else str(Path(answer).expanduser().resolve())


def ask_output_dir(default: Path) -> Path:
    answer = questionary.text("In which folder should the documents be saved?",
                              default=str(default), validate=_not_empty).unsafe_ask()
    path = Path(answer.strip().strip('"')).expanduser()
    if path.suffix.lower() in {".md", ".markdown", ".docx"}:
        path = path.parent  # user gave a file name: use its folder
    return path.resolve()


def _claude_code_settings(previous: Settings | None) -> Settings | None:
    with console.status("Checking Claude Code (installed? logged in?) ..."):
        status = check_claude_code()

    if not status.installed:
        console.print(f"[red]x Claude Code not found.[/] {status.message}\n{CLAUDE_INSTALL_HELP}")
        return None
    console.print(f"[green]v[/] Found Claude Code {status.version or ''} at {status.path}")
    if not status.logged_in:
        console.print(f"[red]x Claude Code is installed but could not answer:[/] {status.message}\n"
                      "Run [bold]claude[/] in a terminal, log in, then try again.")
        return None
    console.print("[green]v[/] Claude Code is logged in and responding.")

    same = previous if previous and previous.backend == BACKEND_CLAUDE_CODE else None
    console.print("[dim]Model can be an alias (haiku, sonnet, opus) or a full model name.[/]")
    fast = questionary.text("Fast model (summarises every file):",
                            default=same.fast_model if same else "haiku", validate=_not_empty).unsafe_ask()
    smart = questionary.text("Smart model (writes the requirements):",
                             default=same.smart_model if same else "sonnet", validate=_not_empty).unsafe_ask()
    return Settings(backend=BACKEND_CLAUDE_CODE, provider="", fast_model=fast.strip(),
                    smart_model=smart.strip(), claude_path=status.path, concurrency=2)


def ask_api_key(settings: Settings) -> str | None:
    """Ask for the key (hidden). Returns the key only if the user typed a new one."""
    provider = get_provider(settings.provider)
    if not provider.key_env:
        return None
    existing = os.environ.get(provider.key_env)
    if existing:
        masked = existing[:6] + "..." + existing[-4:] if len(existing) > 12 else "****"
        if questionary.confirm(f"Found {provider.key_env} in your environment ({masked}). Use it?",
                               default=True).unsafe_ask():
            return None
    optional = provider.id == "compat"
    key = questionary.password(
        f"Enter your {provider.label} API key" + (" (leave empty if not needed):" if optional else ":"),
        validate=(lambda v: True) if optional else _not_empty,
    ).unsafe_ask().strip()
    if key:
        os.environ[provider.key_env] = key  # this process only
    return key or None


def _api_settings(previous: Settings | None, provider_id: str | None = None) -> tuple[Settings, str | None] | None:
    if provider_id is None:
        choices = [Choice(p.label, value=p.id) for p in PROVIDERS if p.id != "ollama"]
        default = previous.provider if previous and previous.backend == BACKEND_API and previous.provider in {
            c.value for c in choices} else None
        provider_id = questionary.select("Which LLM provider do you want to use?", choices=choices,
                                         default=default).unsafe_ask()
    provider = get_provider(provider_id)

    if not is_installed(provider):
        console.print(f"[yellow]![/] {provider.label} needs the Python package [bold]{provider.package}[/].")
        if not questionary.confirm(f"Install {provider.package} now with pip?", default=True).unsafe_ask():
            console.print(f"Install it later with: [bold]pip install {provider.package}[/]")
            return None
        if not install_package(provider):
            console.print(f"[red]x Installation failed.[/] Try: pip install {provider.package}")
            return None
        console.print(f"[green]v[/] Installed {provider.package}")

    same = previous if previous and previous.backend == BACKEND_API and previous.provider == provider.id else None
    base_url = None
    if provider.needs_base_url or provider.default_base_url:
        base_url = questionary.text(
            "Base URL of the API:" if provider.needs_base_url else "Ollama server URL:",
            default=(same.base_url if same and same.base_url else provider.default_base_url or ""),
            validate=_not_empty,
        ).unsafe_ask().strip()

    settings = Settings(backend=BACKEND_API, provider=provider.id, base_url=base_url,
                        concurrency=2 if provider.id == "ollama" else 4)
    new_key = ask_api_key(settings)

    console.print("[dim]Model names change often - check your provider's docs if a suggestion fails.[/]")
    settings.fast_model = questionary.text(
        "Fast model name (cheap, summarises every file):",
        default=same.fast_model if same else provider.fast_hint, validate=_not_empty).unsafe_ask().strip()
    settings.smart_model = questionary.text(
        "Smart model name (strong, writes the requirements):",
        default=same.smart_model if same else provider.smart_hint, validate=_not_empty).unsafe_ask().strip()
    settings.api_key = new_key
    return settings, new_key


def ask_concurrency(default: int) -> int:
    console.print("[dim]More parallel calls = faster, but higher chance of hitting rate limits.[/]")
    answer = questionary.text(
        "How many files should be analysed in parallel? (1-16)", default=str(default),
        validate=lambda v: True if v.strip().isdigit() and 1 <= int(v) <= 16 else "Enter a number from 1 to 16",
    ).unsafe_ask()
    return int(answer.strip())


def test_connection(settings: Settings) -> tuple[bool, str]:
    try:
        for role in ("fast", "smart"):
            model = settings.fast_model if role == "fast" else settings.smart_model
            with console.status(f"Testing {role} model '{model}' ..."):
                ping(build_llm(settings, role))
            console.print(f"[green]v[/] {role.capitalize()} model '{model}' is working.")
        return True, ""
    except Exception as exc:  # show provider errors as-is (bad key, unknown model, ...)
        return False, str(exc)[:600]


def ask_llm_settings(previous: Settings | None = None) -> Settings:
    """Ask the LLM questions until we have a working configuration."""
    while True:
        mode = questionary.select(
            "How do you want to connect to an LLM?",
            choices=[
                Choice("I have an API key (Anthropic, OpenAI, Grok, Gemini, Groq, ...)", value="api"),
                Choice("Use Claude Code already installed on this computer (no API key)", value="claude"),
                Choice("Use a local model with Ollama (free, no API key)", value="ollama"),
            ],
            default="claude" if previous and previous.backend == BACKEND_CLAUDE_CODE else None,
        ).unsafe_ask()

        new_key = None
        if mode == "claude":
            settings = _claude_code_settings(previous)
            if settings is None:
                if questionary.confirm("Choose a different option?", default=True).unsafe_ask():
                    continue
                raise KeyboardInterrupt
            # Claude Code was already verified with a real prompt; only test the chosen models.
        else:
            result = _api_settings(previous, "ollama" if mode == "ollama" else None)
            if result is None:
                continue
            settings, new_key = result

        settings.concurrency = ask_concurrency(settings.concurrency)
        ok, error = test_connection(settings)
        if not ok:
            console.print(f"[red]x Connection test failed:[/]\n{error}")
            action = questionary.select("What do you want to do?", choices=[
                Choice("Change the settings", value="retry"),
                Choice("Continue anyway", value="continue"),
                Choice("Quit", value="quit"),
            ]).unsafe_ask()
            if action == "retry":
                previous = settings
                continue
            if action == "quit":
                raise KeyboardInterrupt

        _offer_save(settings, new_key)
        return settings


def _offer_save(settings: Settings, new_key: str | None) -> None:
    if not questionary.confirm("Save these LLM settings for next time?", default=True).unsafe_ask():
        return
    include_key = False
    if new_key:
        provider = get_provider(settings.provider)
        include_key = questionary.confirm(
            f"Also save the API key? (stored as plain text in {config_file()}; "
            f"the safer option is to set the {provider.key_env} environment variable)",
            default=False,
        ).unsafe_ask()
    path = save_settings(settings, include_api_key=include_key)
    console.print(f"[green]v[/] Settings saved to {path}")


def ensure_api_key(settings: Settings) -> None:
    """Saved settings may not contain the key: ask for it if it is missing."""
    if settings.backend != BACKEND_API:
        return
    provider = get_provider(settings.provider)
    if not provider.key_env or provider.id == "compat":
        return
    if settings.api_key or os.environ.get(provider.key_env):
        if settings.api_key:
            os.environ[provider.key_env] = settings.api_key
        return
    console.print(f"[yellow]![/] No API key found for {provider.label} ({provider.key_env}).")
    settings.api_key = ask_api_key(settings)
