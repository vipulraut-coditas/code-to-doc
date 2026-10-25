"""LLM factory: the ONLY place in the project that knows which provider is used.

Nodes call ``build_llm(settings, "fast" | "smart")`` and get a LangChain
``BaseChatModel``. Switching provider = changing settings, never code.
"""

from __future__ import annotations

import os

from langchain_core.language_models.chat_models import BaseChatModel

from codedoc.config import BACKEND_CLAUDE_CODE, Settings
from codedoc.providers import get_provider, is_installed
from codedoc.text import message_text


class LLMConfigError(RuntimeError):
    pass


def resolve_api_key(settings: Settings) -> str | None:
    provider = get_provider(settings.provider)
    if not provider.key_env:
        return None
    return settings.api_key or os.environ.get(provider.key_env)


def build_llm(settings: Settings, role: str) -> BaseChatModel:
    model = settings.fast_model if role == "fast" else settings.smart_model
    if not model:
        raise LLMConfigError(f"No {role} model configured. Run `codedoc setup`.")

    if settings.backend == BACKEND_CLAUDE_CODE:
        from codedoc.llm_claude_cli import ClaudeCLIChatModel

        return ClaudeCLIChatModel(model=model, claude_path=settings.claude_path)

    provider = get_provider(settings.provider)
    if not is_installed(provider):
        raise LLMConfigError(
            f"{provider.label} needs the '{provider.package}' package. "
            f"Install it with: pip install {provider.package}"
        )

    key = resolve_api_key(settings)
    if provider.key_env and not key and provider.id != "compat":
        raise LLMConfigError(
            f"No API key for {provider.label}. Set the {provider.key_env} environment "
            f"variable or run `codedoc setup`."
        )
    if key and provider.key_env:
        # Every LangChain integration reads its own standard env var.
        os.environ[provider.key_env] = key

    if provider.id == "compat":
        from langchain_openai import ChatOpenAI

        if not settings.base_url:
            raise LLMConfigError("OpenAI-compatible provider needs a base URL.")
        return ChatOpenAI(model=model, base_url=settings.base_url, api_key=key or "not-needed")

    from langchain.chat_models import init_chat_model

    kwargs = dict(provider.extra_kwargs)
    base_url = settings.base_url or provider.default_base_url
    if base_url:
        kwargs["base_url"] = base_url
    return init_chat_model(model, model_provider=provider.id, **kwargs)


def ping(llm: BaseChatModel) -> str:
    """Tiny request used by the wizard and `codedoc doctor` to verify a model works."""
    return message_text(llm.invoke("Reply with exactly: OK")).strip()
