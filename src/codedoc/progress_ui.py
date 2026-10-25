"""Terminal progress display.

Design:
* Every finished file/module is printed as its own log line, so the user can
  see exactly what was analysed and how long it took.
* ONE live progress bar stays at the bottom and shows the files/modules that
  are being analysed right now.
* Live descriptions are kept short, because a line wider than the terminal
  makes the live display redraw itself as duplicate lines.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from rich.console import Console
from rich.progress import (BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID,
                           TextColumn, TimeElapsedColumn, TimeRemainingColumn)
from rich.markup import escape

STEPS = 4


def _symbols(console: Console) -> dict[str, str]:
    """Use nice symbols only if the terminal can print them (old Windows consoles can't)."""
    if (console.encoding or "").lower().replace("-", "").startswith("utf"):
        return {"ok": "✓", "cached": "↺", "fail": "✗", "skip": "•"}
    return {"ok": "+", "cached": "=", "fail": "x", "skip": "-"}


def fmt_seconds(seconds: float) -> str:
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def shorten(text: str, width: int) -> str:
    """Keep the END of a path (the file name is the interesting part)."""
    if width <= 3:
        return ""
    return text if len(text) <= width else "..." + text[-(width - 3):]


class ProgressUI:
    def __init__(self, console: Console, fast_model: str, smart_model: str, concurrency: int = 1,
                 plain: bool = False):
        self.console = console
        # plain = log lines only, no live bar (for CI logs or terminals that redraw badly)
        self.plain = plain or not console.is_terminal or console.is_dumb_terminal
        self.concurrency = concurrency
        self.fast_model = fast_model
        self.smart_model = smart_model
        self.sym = _symbols(console)
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description:<12}"),
            BarColumn(bar_width=24),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            TextColumn("[cyan]{task.fields[current]}"),
            console=console,
            transient=False,
        )
        self._lock = threading.Lock()
        self._active: list[str] = []
        self._done = 0
        self._total = 0
        self._task: TaskID | None = None
        self._stage_started = time.monotonic()
        self._run_started = time.monotonic()

    # ------------------------------------------------------------ context manager
    def __enter__(self) -> "ProgressUI":
        if not self.plain:
            self.progress.__enter__()
        return self

    def __exit__(self, *exc: Any) -> None:
        if not self.plain:
            self.progress.__exit__(*exc)

    # ------------------------------------------------------------ helpers
    def _print(self, message: str) -> None:
        self.progress.console.print(message, highlight=False)

    def _step(self, number: int, title: str) -> None:
        self._print(f"\n[bold cyan]Step {number}/{STEPS}[/]  [bold]{title}[/]")
        self._stage_started = time.monotonic()

    def _new_task(self, description: str, total: int | None) -> None:
        if self._task is not None:
            self.progress.update(self._task, visible=False)
        self._active, self._done, self._total = [], 0, total or 0
        self._task = self.progress.add_task(description, total=total, current="")

    def _current_text(self) -> str:
        if not self._active:
            return ""
        width = max(20, self.console.width - 70)  # ~70 columns are used by the bar
        extra = f" (+{len(self._active) - 1} more)" if len(self._active) > 1 else ""
        return "now: " + escape(shorten(self._active[0], width - len(extra) - 5)) + extra

    def _refresh_current(self) -> None:
        if self._task is not None:
            self.progress.update(self._task, current=self._current_text())

    def _counter(self) -> str:
        width = len(str(self._total))
        return f"[{self._done:>{width}}/{self._total}]"

    # ------------------------------------------------------------ event handler
    def __call__(self, event: str, **data: Any) -> None:
        handler = getattr(self, f"on_{event}", None)
        if handler:
            with self._lock:
                handler(**data)

    def on_scan_start(self, repo: str) -> None:
        self._step(1, "Scanning repository")
        self._print(f"  Folder : {escape(repo)}")
        self._new_task("Scanning", None)

    def on_scan_done(self, files: int, stack: list[str], total_candidates: int, skipped_secrets: int) -> None:
        self.progress.update(self._task, total=1, completed=1)
        self._print(f"  Stack  : {escape(', '.join(stack)) or 'not detected'}")
        selected = f"{files} selected for analysis"
        if total_candidates > files:
            selected += f" (out of {total_candidates}; raise --max-files to include more)"
        self._print(f"  Files  : {selected}")
        if skipped_secrets:
            self._print(f"  Privacy: {skipped_secrets} secret-looking file(s) skipped, never sent to the LLM")
        self._step(2, f"Reading files  [dim](fast model: {escape(self.fast_model)}, "
                      f"{self.concurrency} at a time)[/]")
        self._new_task("Files", files)

    def on_file_start(self, path: str, module: str) -> None:
        self._active.append(path)
        self._refresh_current()

    def on_file_done(self, path: str, cached: bool, ok: bool, seconds: float, error: str | None = None) -> None:
        if path in self._active:
            self._active.remove(path)
        self._done += 1
        counter = self._counter()
        if cached:
            self._print(f"  [blue]{self.sym['cached']}[/] {counter} {escape(path)}  [dim]cached, unchanged[/]")
        elif ok:
            self._print(f"  [green]{self.sym['ok']}[/] {counter} {escape(path)}  [dim]{fmt_seconds(seconds)}[/]")
        else:
            self._print(f"  [red]{self.sym['fail']}[/] {counter} {escape(path)}  [red]failed:[/] {escape(error or '')}")
        self.progress.advance(self._task)
        self._refresh_current()

    def on_modules_start(self, modules: int) -> None:
        self._print(f"  [dim]Files done in {fmt_seconds(time.monotonic() - self._stage_started)}[/]")
        self._step(3, f"Understanding modules / feature areas  [dim](fast model: {escape(self.fast_model)})[/]")
        self._new_task("Modules", modules)

    def on_module_start(self, module: str, files: int) -> None:
        self._active.append(module)
        self._refresh_current()

    def on_module_done(self, module: str, files: int, merged: bool, ok: bool, seconds: float,
                       error: str | None = None) -> None:
        if module in self._active:
            self._active.remove(module)
        self._done += 1
        counter = self._counter()
        label = f"{escape(module)} [dim]({files} file{'s' if files != 1 else ''})[/]"
        if not merged:
            self._print(f"  [blue]{self.sym['skip']}[/] {counter} {label}  [dim]single file, no merge needed[/]")
        elif ok:
            self._print(f"  [green]{self.sym['ok']}[/] {counter} {label}  [dim]{fmt_seconds(seconds)}[/]")
        else:
            self._print(f"  [red]{self.sym['fail']}[/] {counter} {label}  [red]failed:[/] {escape(error or '')}")
        self.progress.advance(self._task)
        self._refresh_current()

    def on_requirements_start(self, modules: int) -> None:
        self._step(4, f"Writing requirements like a Business Analyst  [dim](smart model: {escape(self.smart_model)})[/]")
        self._print(f"  Reasoning over {modules} module summaries. This is one long call, usually 1-5 minutes...")
        if self.plain:
            self._print("  [dim]Still working - no output until the model answers.[/]")
        self._new_task("Thinking", None)
        self.progress.update(self._task, current="actors, features, FR/NFR, rules, open questions")

    def on_requirements_done(self, requirements: int, nfrs: int, seconds: float) -> None:
        self.progress.update(self._task, total=1, completed=1, current="")
        self._print(f"  [green]{self.sym['ok']}[/] {requirements} functional + {nfrs} non-functional "
                    f"requirements  [dim]{fmt_seconds(seconds)}[/]")

    def on_render_done(self) -> None:
        if self._task is not None:
            self.progress.update(self._task, visible=False)
        self._print(f"  [green]{self.sym['ok']}[/] SRS document rendered  "
                    f"[dim]total time {fmt_seconds(time.monotonic() - self._run_started)}[/]")
