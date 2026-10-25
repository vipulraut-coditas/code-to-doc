"""Command line interface.

    codedoc                      interactive: asks everything, then generates the SRS
    codedoc setup                only configure the LLM (and save it)
    codedoc generate REPO [-o]   non-interactive, uses saved settings / env vars (CI friendly)
    codedoc doctor               show settings and test the LLM connection
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel

from codedoc import __version__
from codedoc.config import BACKEND_API, BACKEND_CLAUDE_CODE, Settings, apply_env_overrides, load_settings
from codedoc.llm import LLMConfigError

console = Console()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codedoc",
                                     description="AI Business Analyst: turns any code repository into an SRS document.")
    parser.add_argument("--version", action="version", version=f"codedoc {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="configure the LLM (API key / Claude Code, provider, models)")
    sub.add_parser("doctor", help="show current settings and test the LLM connection")

    gen = sub.add_parser("generate", help="generate an SRS without questions (uses saved settings)")
    gen.add_argument("repo", help="local folder or git URL")
    gen.add_argument("-o", "--output", help="output Markdown file (default: <repo>/docs/SRS.md)")
    gen.add_argument("--backend", choices=[BACKEND_API, BACKEND_CLAUDE_CODE])
    gen.add_argument("--provider", help="anthropic, openai, xai, google_genai, groq, ollama, compat, ...")
    gen.add_argument("--fast-model")
    gen.add_argument("--smart-model")
    gen.add_argument("--max-files", type=int)
    gen.add_argument("--concurrency", type=int)
    gen.add_argument("--no-cache", action="store_true", help="ignore cached file summaries")
    gen.add_argument("--plain", action="store_true",
                     help="log lines only, no live progress bar (CI, or terminals that redraw badly)")
    return parser


# ---------------------------------------------------------------- generation with progress bars
def run_generation(repo: str, output: Path | None, settings: Settings, use_cache: bool = True,
                   plain: bool = False) -> int:
    from codedoc.api import generate_srs

    from codedoc.progress_ui import ProgressUI

    plain = plain or os.environ.get("CODEDOC_PLAIN", "").lower() in {"1", "true", "yes"}
    with ProgressUI(console, settings.fast_model, settings.smart_model, settings.concurrency, plain=plain) as ui:
        result = generate_srs(repo, output, settings, on_progress=ui, use_cache=use_cache)

    console.print(Panel.fit(
        f"[bold green]SRS ready![/]\n{result.output_path}\n\n"
        f"Files analysed: {result.files_analysed}   Functional requirements: {result.functional_requirements}",
        title="codedoc"))
    for w in [w for w in result.warnings if "secret-looking" not in w][:5]:
        console.print(f"[yellow]note:[/] {w}")
    return 0


# ---------------------------------------------------------------- commands
def cmd_interactive() -> int:
    import questionary

    from codedoc.api import default_output_path
    from codedoc.wizard import ask_llm_settings, ask_output, ask_repo, ensure_api_key, settings_table

    console.print(Panel.fit("[bold]codedoc[/] - your AI Business Analyst\n"
                            "Reads a code repository and writes an SRS document.", border_style="cyan"))
    repo = ask_repo()

    saved = load_settings()
    if saved and saved.is_complete():
        console.print("\nSaved LLM settings:")
        console.print(settings_table(saved))
        settings = saved if questionary.confirm("Use these settings?", default=True).unsafe_ask() \
            else ask_llm_settings(saved)
    else:
        settings = ask_llm_settings(saved)
    ensure_api_key(settings)

    output = ask_output(default_output_path(repo))
    console.print()
    console.print(settings_table(settings, repo, output))
    if not questionary.confirm("Start generating the SRS?", default=True).unsafe_ask():
        return 0
    return run_generation(repo, output, settings)


def cmd_setup() -> int:
    from codedoc.wizard import ask_llm_settings

    ask_llm_settings(load_settings())
    return 0


def cmd_doctor() -> int:
    from codedoc.config import config_file
    from codedoc.wizard import settings_table, test_connection

    settings = apply_env_overrides(load_settings() or Settings())
    console.print(f"Config file: {config_file()}")
    if not settings.is_complete():
        console.print("[yellow]Not configured yet.[/] Run [bold]codedoc setup[/].")
        return 1
    console.print(settings_table(settings))
    ok, error = test_connection(settings)
    if not ok:
        console.print(f"[red]x[/] {error}")
    return 0 if ok else 1


def cmd_generate(args: argparse.Namespace) -> int:
    settings = apply_env_overrides(load_settings() or Settings())
    for attr in ("backend", "provider", "fast_model", "smart_model", "max_files", "concurrency"):
        value = getattr(args, attr)
        if value:
            setattr(settings, attr, value)
    if not settings.is_complete():
        console.print("[red]LLM is not configured.[/] Run [bold]codedoc setup[/] or pass "
                      "--backend/--provider/--fast-model/--smart-model.")
        return 2
    output = Path(args.output) if args.output else None
    return run_generation(args.repo, output, settings, use_cache=not args.no_cache, plain=args.plain)


def main(argv: list[str] | None = None) -> int:
    load_dotenv(find_dotenv(usecwd=True))  # lets users keep API keys in a local .env file
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup":
            return cmd_setup()
        if args.command == "doctor":
            return cmd_doctor()
        if args.command == "generate":
            return cmd_generate(args)
        return cmd_interactive()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/]")
        return 130
    except (LLMConfigError, FileNotFoundError) as exc:
        console.print(f"[red]Error:[/] {exc}")
        return 2


def run() -> None:
    sys.exit(main())
