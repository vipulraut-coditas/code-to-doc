import io

from rich.console import Console

from codedoc.api import generate_docs
from codedoc.config import Settings
from codedoc.progress_ui import ProgressUI, fmt_seconds, shorten


def test_helpers():
    assert fmt_seconds(5) == "5s"
    assert fmt_seconds(125) == "2m 05s"
    assert fmt_seconds(3725) == "1h 02m"
    assert shorten("app/services/loan_service.py", 15) == "...n_service.py"
    assert shorten("short.py", 15) == "short.py"


def test_progress_ui_logs_every_file_and_module(sample_repo, tmp_path, fake_llm):
    buffer = io.StringIO()
    console = Console(file=buffer, width=100, force_terminal=False, color_system=None)
    settings = Settings(backend="api", provider="anthropic", fast_model="fast-x", smart_model="smart-y")

    with ProgressUI(console, "fast-x", "smart-y", 3) as ui:
        result = generate_docs(str(sample_repo), ["srs", "api"], tmp_path / "s", settings,
                               fast_llm=fake_llm, smart_llm=fake_llm, on_progress=ui)

    out = buffer.getvalue()
    for step in ("Step 1/4", "Step 2/4", "Step 3/4", "Step 4/4"):
        assert step in out
    assert "app/orders.py" in out and "app/api/routes.py" in out      # every file is logged
    assert f"[{result.files_analysed}/{result.files_analysed}]" in out  # counter reaches the end
    assert "single file, no merge needed" in out                       # module log
    assert "Writing 2 documents" in out
    assert "Software Requirements Specification (SRS)" in out and "1 functional + 1 non-functional" in out
    assert "API Documentation" in out and "1 endpoints, 1 data models" in out
    assert "secret-looking" in out
