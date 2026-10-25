"""Command line interface.

    codedoc                      interactive: asks which documents and formats, then everything else
    codedoc setup                only configure the LLM (and save it)
    codedoc generate REPO [--doc srs,api] [--format md,docx,gdoc] [-o DIR]
                                 non-interactive, uses saved settings / env vars (CI friendly)
    codedoc doctor               show settings and test the LLM connection
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from codedoc import __version__
from codedoc.config import BACKEND_API, BACKEND_CLAUDE_CODE, Settings, apply_env_overrides, load_settings
from codedoc.doctypes import DOC_TYPE_IDS, parse_doc_types
from codedoc.formats import FORMAT_IDS, GoogleSetupError, get_format, needs_output_dir, parse_formats
from codedoc.llm import LLMConfigError

console = Console()


def _as_arg(parse):
    def convert(value: str) -> list[str]:
        try:
            return parse(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from None
    return convert


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codedoc",
                                     description="Turns any code repository into software documentation "
                                                 "(SRS, user manual, API, technical and design documents) "
                                                 "as Markdown, Word or Google Docs.")
    parser.add_argument("--version", action="version", version=f"codedoc {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="configure the LLM (API key / Claude Code, provider, models)")
    sub.add_parser("doctor", help="show current settings and test the LLM connection")

    gen = sub.add_parser("generate", help="generate documents without questions (uses saved settings)")
    gen.add_argument("repo", help="local folder or git URL")
    gen.add_argument("-d", "--doc", default="srs", type=_as_arg(parse_doc_types),
                     help=f"comma-separated document types: {', '.join(DOC_TYPE_IDS)} or all (default: srs)")
    gen.add_argument("-f", "--format", default="md", type=_as_arg(parse_formats),
                     help=f"comma-separated output formats: {', '.join(FORMAT_IDS)} or all (default: md)")
    gen.add_argument("-o", "--output-dir", help="folder for the .md / .docx files (default: <repo>/docs)")
    gen.add_argument("--gdrive-folder", help="Google Drive folder id for Google Docs output (default: My Drive)")
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
def run_generation(repo: str, doc_types: list[str], output_dir: Path | None, settings: Settings,
                   use_cache: bool = True, plain: bool = False, formats: list[str] | None = None,
                   google_folder: str | None = None) -> int:
    from codedoc.api import generate_docs

    from codedoc.progress_ui import ProgressUI

    formats = formats or ["md"]
    plain = plain or os.environ.get("CODEDOC_PLAIN", "").lower() in {"1", "true", "yes"}
    with ProgressUI(console, settings.fast_model, settings.smart_model, settings.concurrency, plain=plain) as ui:
        result = generate_docs(repo, doc_types, output_dir, settings, formats=formats, google_folder=google_folder,
                               on_progress=ui, use_cache=use_cache)

    ok = [d for d in result.documents if d.ok and d.outputs]
    lines = []
    for d in result.documents:
        if not d.ok:
            lines.append(f"[red]x[/] {escape(d.label)}  [red]failed[/]")
            continue
        lines.append(f"[green]v[/] {escape(d.label)}")
        for fmt_id in formats:
            where = d.outputs.get(fmt_id)
            fmt = get_format(fmt_id)
            shown = (Path(where).name if fmt.local else where) if where else None  # folder is shown once below
            lines.append(f"    {fmt.extension or 'Google Docs':<12} " + (escape(shown) if shown else "[red]failed[/]"))
    title = "[bold green]Documents ready![/]" if len(ok) == len(result.documents) else \
        f"[bold yellow]{len(ok)} of {len(result.documents)} documents ready[/]"
    footer = f"\n\nFolder: {escape(str(result.output_dir))}" if result.output_dir else "\n"
    console.print(Panel.fit(f"{title}\n" + "\n".join(lines) + footer + f"\nFiles analysed: {result.files_analysed}",
                            title="codedoc"))
    for w in [w for w in result.warnings if "secret-looking" not in w][:5]:
        console.print(f"[yellow]note:[/] {escape(w)}")
    return 0 if ok else 1


# ---------------------------------------------------------------- commands
def cmd_interactive() -> int:
    import questionary

    from codedoc.api import default_output_dir
    from codedoc.wizard import (ask_doc_types, ask_formats, ask_llm_settings, ask_output_dir, ask_repo,
                                ensure_api_key, settings_table)

    console.print(Panel.fit("[bold]codedoc[/] - your AI documentation agent\n"
                            "Reads a code repository and writes SRS, user manual, API, technical\n"
                            "and design documents as Markdown, Word or Google Docs.", border_style="cyan"))
    doc_types = ask_doc_types()
    formats = ask_formats()
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

    output_dir = ask_output_dir(default_output_dir(repo)) if needs_output_dir(formats) else None
    console.print()
    console.print(settings_table(settings, repo, output_dir, doc_types, formats))
    count = len(doc_types)
    if not questionary.confirm(f"Start generating {count} document{'s' if count != 1 else ''}?",
                               default=True).unsafe_ask():
        return 0
    return run_generation(repo, doc_types, output_dir, settings, formats=formats)


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
    output_dir = Path(args.output_dir) if args.output_dir else None
    return run_generation(args.repo, args.doc, output_dir, settings, use_cache=not args.no_cache, plain=args.plain,
                          formats=args.format, google_folder=args.gdrive_folder)


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
    except (LLMConfigError, FileNotFoundError, GoogleSetupError) as exc:
        console.print(f"[red]Error:[/] {escape(str(exc))}")
        return 2


def run() -> None:
    sys.exit(main())
