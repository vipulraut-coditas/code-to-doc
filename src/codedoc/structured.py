"""Provider-independent structured output.

Not every model supports tool calling / ``with_structured_output`` (the Claude
Code CLI and many local models don't). So we ask for JSON in the prompt,
parse it ourselves, and retry once with the error message if it is invalid.
This works the same on every provider.
"""

from __future__ import annotations

import json
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from codedoc.prompts import FIX_JSON, SCHEMA_SUFFIX, SYSTEM_BA
from codedoc.text import extract_json, message_text

T = TypeVar("T", bound=BaseModel)


def invoke_structured(llm: BaseChatModel, prompt: str, schema: type[T], *,
                      system: str = SYSTEM_BA, retries: int = 1) -> T:
    schema_json = json.dumps(schema.model_json_schema(), separators=(",", ":"))
    messages = [SystemMessage(content=system),
                HumanMessage(content=prompt + SCHEMA_SUFFIX.format(schema=schema_json))]

    last_error: Exception | None = None
    for _ in range(retries + 1):
        reply = message_text(llm.invoke(messages))
        try:
            return schema.model_validate(extract_json(reply))
        except (ValueError, ValidationError, RecursionError) as exc:  # RecursionError: absurdly nested JSON
            last_error = exc
            messages += [AIMessage(content=reply),
                         HumanMessage(content=FIX_JSON.format(error=str(exc)[:800]))]
    raise ValueError(f"Model did not return valid JSON for {schema.__name__}: {last_error}")
