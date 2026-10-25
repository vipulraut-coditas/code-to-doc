"""Interactive questions shown when a user runs ``codedoc``.

Flow:
  1. Which document(s) should be generated?         (one, all, or several via a checkbox)
  2. Which project should be documented?            (folder or git URL)
  3. API key or the installed Claude Code?           (Claude Code is verified)
  4. Which LLM provider?                             (API path only)
  5. API key                                         (hidden input)
  6. Fast model name / Smart model name
  7. Connection test
  8. Output folder for the documents
  9. Save settings for next time?
"""

from __future__ import annotations

import os
from pathlib import Path

import questionary
from questionary import Choice
from rich.console import Console
from rich.table import Table

from codedoc.config import BACKEND_API, BACKEND_CLAUDE_CODE, Settings, config_file, save_settings
from codedoc.doctypes import DOC_TYPES, get_doc_type, parse_doc_types
from codedoc.llm import build_llm, ping
from codedoc.llm_claude_cli import check_claude_code
from codedoc.providers import PROVIDERS, get_provider, install_package, is_installed
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
                   doc_types: list[str] | None = None) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    if doc_types:
        table.add_row("Documents", "\n".join(get_doc_type(d).label for d in doc_types))
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
def ask_doc_types() -> list[str]:
    """Arrow + Enter picks exactly the highlighted document; several documents need an explicit checkbox."""
    choice = questionary.select(
        "Which document do you want to generate?",
        choices=[Choice(f"{d.label}  -  {d.description}", value=d.id) for d in DOC_TYPES]
        + [Choice("All documents", value="all"),
           Choice("Several documents (choose with a checkbox) ...", value="several")],
    ).unsafe_ask()
    if choice == "several":
        choice = questionary.checkbox(
            "Which documents should I generate?",
            choices=[Choice(f"{d.label}  -  {d.description}", value=d.id) for d in DOC_TYPES],
            instruction="(Space = tick/untick, Enter = confirm)",
            validate=lambda picked: True if picked else "Tick at least one document with Space",
        ).unsafe_ask()
    doc_types = parse_doc_types(choice)
    console.print("[green]v[/] Will generate: " + ", ".join(get_doc_type(d).label for d in doc_types))
    return doc_types


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
    if path.suffix.lower() in {".md", ".markdown"}:
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
