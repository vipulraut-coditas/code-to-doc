"""Registry of supported LLM providers.

Adding a new provider = adding one ``Provider(...)`` entry here. Every provider
that LangChain's ``init_chat_model`` knows about can be added this way.
Model names are only *suggestions* shown in the setup wizard; providers rename
models often, so always check the provider's docs for current names.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    id: str                       # provider id understood by init_chat_model ("compat" is ours)
    label: str                    # shown in the wizard
    package: str                  # pip package with the LangChain integration
    module: str                   # import name of that package
    key_env: str | None           # env var holding the API key (None = no key needed)
    fast_hint: str                # suggested cheap model
    smart_hint: str               # suggested strong model
    default_base_url: str | None = None
    needs_base_url: bool = False
    extra_kwargs: dict = field(default_factory=dict)


PROVIDERS: list[Provider] = [
    Provider("anthropic", "Anthropic (Claude)", "langchain-anthropic", "langchain_anthropic",
             "ANTHROPIC_API_KEY", "claude-haiku-5-5", "claude-sonnet-5-5",
             extra_kwargs={"max_tokens": 16000}),
    Provider("openai", "OpenAI (GPT)", "langchain-openai", "langchain_openai",
             "OPENAI_API_KEY", "gpt-5-mini", "gpt-5.5"),
    Provider("xai", "xAI (Grok)", "langchain-xai", "langchain_xai",
             "XAI_API_KEY", "grok-3-mini", "grok-4"),
    Provider("google_genai", "Google (Gemini)", "langchain-google-genai", "langchain_google_genai",
             "GOOGLE_API_KEY", "gemini-2.5-flash", "gemini-2.5-pro"),
    Provider("groq", "Groq (fast open models)", "langchain-groq", "langchain_groq",
             "GROQ_API_KEY", "llama-3.1-8b-instant", "llama-3.3-70b-versatile"),
    Provider("deepseek", "DeepSeek", "langchain-deepseek", "langchain_deepseek",
             "DEEPSEEK_API_KEY", "deepseek-chat", "deepseek-chat"),
    Provider("mistralai", "Mistral AI", "langchain-mistralai", "langchain_mistralai",
             "MISTRAL_API_KEY", "mistral-small-latest", "mistral-large-latest"),
    Provider("ollama", "Ollama (local models, no API key)", "langchain-ollama", "langchain_ollama",
             None, "llama3.1", "qwen2.5-coder", default_base_url="http://localhost:11434"),
    Provider("compat", "Any OpenAI-compatible API (OpenRouter, LM Studio, vLLM, Together...)",
             "langchain-openai", "langchain_openai", "CODEDOC_COMPAT_API_KEY",
             "", "", needs_base_url=True),
]

_BY_ID = {p.id: p for p in PROVIDERS}


def get_provider(provider_id: str) -> Provider:
    try:
        return _BY_ID[provider_id]
    except KeyError:
        known = ", ".join(_BY_ID)
        raise ValueError(f"Unknown provider '{provider_id}'. Known providers: {known}") from None


def is_installed(provider: Provider) -> bool:
    return importlib.util.find_spec(provider.module) is not None


def install_package(provider: Provider) -> bool:
    """pip-install the provider's integration into the current Python environment."""
    result = subprocess.run([sys.executable, "-m", "pip", "install", provider.package])
    importlib.invalidate_caches()
    return result.returncode == 0 and is_installed(provider)
