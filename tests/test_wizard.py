import pytest
import questionary
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput

from codedoc import wizard
from codedoc.doctypes import DOC_TYPE_IDS

DOWN, SPACE, ENTER = "\x1b[B", " ", "\r"


@pytest.fixture
def keys(monkeypatch):
    """Feed keystrokes to the questionary prompts used by the wizard."""
    with create_pipe_input() as inp:
        for name in ("select", "checkbox", "text"):
            original = getattr(questionary, name)
            monkeypatch.setattr(wizard.questionary, name,
                                lambda *a, _o=original, **k: _o(*a, input=inp, output=DummyOutput(), **k))
        yield inp.send_text


def test_highlighted_document_is_generated(keys):
    keys(DOWN * 2 + ENTER)  # the 3rd option, no Space needed
    assert wizard.ask_doc_types() == ["api"]


def test_enter_on_first_option(keys):
    keys(ENTER)
    assert wizard.ask_doc_types() == ["srs"]


def test_all_documents(keys):
    keys(DOWN * len(DOC_TYPE_IDS) + ENTER)
    assert wizard.ask_doc_types() == DOC_TYPE_IDS


def test_several_documents_with_checkbox(keys):
    keys(DOWN * (len(DOC_TYPE_IDS) + 1) + ENTER       # "Several documents ..."
         + DOWN + SPACE + DOWN * 3 + SPACE + ENTER)   # tick user_manual and design
    assert wizard.ask_doc_types() == ["user_manual", "design"]


def test_repo_prompt_starts_empty(keys, tmp_path):
    keys(str(tmp_path) + ENTER)  # typed text is the whole answer: nothing pre-filled to delete
    assert wizard.ask_repo() == str(tmp_path.resolve())


def test_repo_prompt_rejects_empty_answer(keys, tmp_path):
    keys(ENTER + str(tmp_path) + ENTER)  # bare Enter is refused, the prompt stays open
    assert wizard.ask_repo() == str(tmp_path.resolve())


def test_several_documents_needs_at_least_one_tick(keys):
    keys(DOWN * (len(DOC_TYPE_IDS) + 1) + ENTER
         + ENTER                                      # nothing ticked: rejected, prompt stays open
         + DOWN * 3 + SPACE + ENTER)
    assert wizard.ask_doc_types() == ["technical"]


def test_format_word(keys):
    keys(DOWN + ENTER)
    assert wizard.ask_formats() == ["docx"]


def test_several_formats(keys):
    keys(DOWN * 4 + ENTER + SPACE + DOWN + SPACE + ENTER)  # "Several formats ...", tick Markdown + Word
    assert wizard.ask_formats() == ["md", "docx"]


def test_google_docs_signs_in_up_front(keys, monkeypatch):
    calls = []
    monkeypatch.setattr(wizard, "ensure_google_ready", lambda: calls.append("google") or True)
    keys(DOWN * 2 + ENTER)
    assert wizard.ask_formats() == ["gdoc"] and calls == ["google"]


def test_google_docs_falls_back_to_markdown_when_setup_is_skipped(keys, monkeypatch):
    monkeypatch.setattr(wizard, "ensure_google_ready", lambda: False)
    keys(DOWN * 2 + ENTER)
    assert wizard.ask_formats() == ["md"]
