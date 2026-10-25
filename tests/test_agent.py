import pytest

from codedoc.api import generate_srs
from codedoc.config import Settings
from codedoc.schemas import FileSummary
from codedoc.structured import invoke_structured
from codedoc.text import extract_json

from conftest import FakeBA


def settings():
    return Settings(backend="api", provider="anthropic", fast_model="f", smart_model="s", concurrency=3)


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('Here you go:\n```json\n{"a": 2}\n```') == {"a": 2}
    assert extract_json('blah {"a": 3} blah') == {"a": 3}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_invoke_structured_retries_once():
    llm = FakeBA(calls={}, bad_first_reply=True)
    result = invoke_structured(llm, "TASK: summarize_file", FileSummary)
    assert result.purpose == "Handles orders"
    assert llm.calls == {"summarize_file": 1, "fix": 1}


def test_end_to_end_generates_srs(sample_repo, tmp_path, fake_llm):
    events = []
    out = tmp_path / "out" / "SRS.md"
    result = generate_srs(str(sample_repo), out, settings(), fast_llm=fake_llm, smart_llm=fake_llm,
                          on_progress=lambda e, **d: events.append(e))

    md = out.read_text(encoding="utf-8")
    assert result.output_path == out.resolve()
    assert "# Software Requirements Specification" in md
    assert "FR-001" in md and "NFR-001" in md
    assert "Only logged-in users \\| can order." in md  # pipes escaped in tables
    assert "Are refunds supported?" in md
    assert result.functional_requirements == 1
    assert fake_llm.calls["summarize_file"] == result.files_analysed
    assert fake_llm.calls["infer_requirements"] == 1
    assert {"scan_done", "file_done", "modules_start", "requirements_done", "render_done"} <= set(events)


def test_cache_skips_unchanged_files(sample_repo, tmp_path):
    first = FakeBA(calls={})
    generate_srs(str(sample_repo), tmp_path / "a.md", settings(), fast_llm=first, smart_llm=first)
    assert first.calls["summarize_file"] > 0

    second = FakeBA(calls={})
    generate_srs(str(sample_repo), tmp_path / "b.md", settings(), fast_llm=second, smart_llm=second)
    assert "summarize_file" not in second.calls  # everything came from the cache

    (sample_repo / "app" / "orders.py").write_text("def create_order(total, user): ...\n")
    third = FakeBA(calls={})
    generate_srs(str(sample_repo), tmp_path / "c.md", settings(), fast_llm=third, smart_llm=third)
    assert third.calls["summarize_file"] == 1  # only the changed file


def test_empty_repo_still_renders(tmp_path, fake_llm):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = generate_srs(str(empty), tmp_path / "e.md", settings(), fast_llm=fake_llm, smart_llm=fake_llm)
    assert result.files_analysed == 0
    assert "Software Requirements Specification" in result.markdown
