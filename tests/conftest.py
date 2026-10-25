import json
import threading
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

FILE_REPLY = {"purpose": "Handles orders", "key_elements": ["create_order"],
              "business_logic": ["Order total must be positive"], "entities": ["Order"], "integrations": []}
MODULE_REPLY = {"purpose": "Order management", "capabilities": ["Place an order"],
                "business_rules": ["Total > 0"], "entities": ["Order"], "integrations": [], "actors": ["Customer"]}
SRS_REPLY = {
    "project_name": "shop", "purpose": "Lets customers buy products.", "scope": "Online ordering.",
    "product_overview": "A small web shop.",
    "actors": [{"name": "Customer", "description": "Buys products"}],
    "features": [{"name": "Ordering", "description": "Placing orders"}],
    "functional_requirements": [{"id": "FR-001", "feature": "Ordering",
                                 "statement": "The system shall let a customer place an order.",
                                 "priority": "Must", "confidence": "High", "sources": ["app/orders.py"]}],
    "non_functional_requirements": [{"id": "NFR-001", "category": "Security",
                                     "statement": "Only logged-in users | can order.", "confidence": "Medium"}],
    "business_rules": ["Order total must be positive"],
    "data_entities": [{"name": "Order", "description": "A purchase", "key_attributes": ["id", "total"]}],
    "external_interfaces": [], "assumptions": ["Single currency"],
    "open_questions": ["Are refunds supported?"], "glossary": [{"term": "SKU", "definition": "Stock unit"}],
}


class FakeBA(BaseChatModel):
    """Answers based on the TASK tag in the prompt; counts calls per task."""

    calls: dict = {}
    bad_first_reply: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake-ba"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prompt = "\n".join(str(m.content) for m in messages)
        last = str(messages[-1].content)
        if "could not be parsed" in last:
            task = "fix"
        elif "TASK: summarize_file" in prompt:
            task = "summarize_file"
        elif "TASK: summarize_module" in prompt:
            task = "summarize_module"
        else:
            task = "infer_requirements"
        with threading.Lock():
            self.calls[task] = self.calls.get(task, 0) + 1
        if self.bad_first_reply and task != "fix":
            text = "Sure! here is something that is not json"
        else:
            reply = {"summarize_file": FILE_REPLY, "summarize_module": MODULE_REPLY,
                     "infer_requirements": SRS_REPLY, "fix": FILE_REPLY}[task]
            text = "```json\n" + json.dumps(reply) + "\n```"
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


@pytest.fixture
def fake_llm():
    return FakeBA(calls={})


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEDOC_HOME", str(tmp_path / "codedoc-home"))


@pytest.fixture
def sample_repo(tmp_path) -> Path:
    root = tmp_path / "shop"
    files = {
        "README.md": "# Shop\nA tiny shop.",
        "requirements.txt": "fastapi\nsqlalchemy\n",
        "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "app/orders.py": "def create_order(total):\n    assert total > 0\n",
        "app/models.py": "class Order: ...\n",
        "app/api/routes.py": "@app.post('/orders')\ndef post(): ...\n",
        "tests/test_orders.py": "def test_x(): pass\n",
        ".env": "SECRET=1",
        "config/credentials.json": "{}",
        "node_modules/lib/index.js": "x",
        "build/out.py": "ignored by gitignore too",
        ".gitignore": "build/\n*.log\n",
        "debug.log": "noise",
        "package-lock.json": "{}",
    }
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return root
