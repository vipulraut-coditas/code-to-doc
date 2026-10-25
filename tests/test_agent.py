import pytest

from codedoc.api import generate_docs
from codedoc.cli import build_parser
from codedoc.doctypes import DOC_TYPE_IDS, parse_doc_types
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
    out_dir = tmp_path / "out"
    result = generate_docs(str(sample_repo), ["srs"], out_dir, settings(), fast_llm=fake_llm, smart_llm=fake_llm,
                           on_progress=lambda e, **d: events.append(e))

    out = out_dir / "SRS.md"
    md = out.read_text(encoding="utf-8")
    srs = result.get("srs")
    assert srs.ok and srs.output_path == out.resolve()
    assert "# Software Requirements Specification" in md
    assert "FR-001" in md and "NFR-001" in md
    assert "Only logged-in users \\| can order." in md  # pipes escaped in tables
    assert "Are refunds supported?" in md
    assert len(srs.data["functional_requirements"]) == 1
    assert fake_llm.calls["summarize_file"] == result.files_analysed
    assert fake_llm.calls["write_srs"] == 1
    assert [d.doc_type for d in result.documents] == ["srs"]
    assert {"scan_done", "file_done", "modules_start", "documents_start", "document_done"} <= set(events)


def test_generates_all_document_types_from_one_analysis(sample_repo, tmp_path, fake_llm):
    result = generate_docs(str(sample_repo), "all", tmp_path / "docs", settings(),
                           fast_llm=fake_llm, smart_llm=fake_llm)

    assert [d.doc_type for d in result.documents] == DOC_TYPE_IDS
    assert all(d.ok for d in result.documents)
    files = {p.name: p.read_text(encoding="utf-8") for p in (tmp_path / "docs").iterdir()}
    assert set(files) == {"SRS.md", "USER_MANUAL.md", "API.md", "TECHNICAL.md", "DESIGN.md"}
    assert "# User Manual" in files["USER_MANUAL.md"] and "1. Add items to the cart" in files["USER_MANUAL.md"]
    assert "#### `POST /orders`" in files["API.md"] and "| total | body | number | Yes |" in files["API.md"]
    assert "# Technical Documentation" in files["TECHNICAL.md"] and "### 6.1 Orders" in files["TECHNICAL.md"]
    assert "```mermaid\nflowchart LR" in files["DESIGN.md"] and "Use FastAPI" in files["DESIGN.md"]
    # the code is read once, whatever the number of documents
    assert fake_llm.calls["summarize_file"] == result.files_analysed
    for task in ("write_srs", "write_user_manual", "write_api_doc", "write_technical_doc", "write_design_doc"):
        assert fake_llm.calls[task] == 1


def test_one_failing_document_does_not_stop_the_others(sample_repo, tmp_path):
    llm = FakeBA(calls={}, fail_tasks={"write_api_doc"})
    result = generate_docs(str(sample_repo), ["srs", "api"], tmp_path / "docs", settings(),
                           fast_llm=llm, smart_llm=llm)

    assert result.get("srs").ok and (tmp_path / "docs" / "SRS.md").exists()
    api = result.get("api")
    assert not api.ok and api.output_path is None and api.error
    assert not (tmp_path / "docs" / "API.md").exists()
    assert any("API Documentation" in w for w in result.warnings)


def test_doc_type_parsing():
    assert parse_doc_types("api, srs") == ["srs", "api"]  # menu order, trimmed
    assert parse_doc_types(["design", "design"]) == ["design"]
    assert parse_doc_types("all") == DOC_TYPE_IDS
    with pytest.raises(ValueError, match="Choose from"):
        parse_doc_types("srs,foo")
    with pytest.raises(ValueError):
        parse_doc_types("")
    assert build_parser().parse_args(["generate", "."]).doc == ["srs"]
    assert build_parser().parse_args(["generate", ".", "--doc", "user_manual,api"]).doc == ["user_manual", "api"]
    with pytest.raises(SystemExit):
        build_parser().parse_args(["generate", ".", "--doc", "foo"])


def test_cache_skips_unchanged_files(sample_repo, tmp_path):
    first = FakeBA(calls={})
    generate_docs(str(sample_repo), ["srs"], tmp_path / "a", settings(), fast_llm=first, smart_llm=first)
    assert first.calls["summarize_file"] > 0

    second = FakeBA(calls={})
    generate_docs(str(sample_repo), ["srs"], tmp_path / "b", settings(), fast_llm=second, smart_llm=second)
    assert "summarize_file" not in second.calls  # everything came from the cache

    (sample_repo / "app" / "orders.py").write_text("def create_order(total, user): ...\n")
    third = FakeBA(calls={})
    generate_docs(str(sample_repo), ["srs"], tmp_path / "c", settings(), fast_llm=third, smart_llm=third)
    assert third.calls["summarize_file"] == 1  # only the changed file


def test_empty_repo_still_renders(tmp_path, fake_llm):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = generate_docs(str(empty), "all", tmp_path / "e", settings(), fast_llm=fake_llm, smart_llm=fake_llm)
    assert result.files_analysed == 0
    assert all(d.ok for d in result.documents)
    assert "Software Requirements Specification" in result.get("srs").markdown
