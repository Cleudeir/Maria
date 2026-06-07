from agentic.provider.base import LLMProvider
from agentic.provider.llamacpp import LlamaCppProvider
from agentic.provider.local_llm import LocalLLMProvider
from agentic.provider.opencode import OpenCodeProvider, OPENCODE_URL, OPENCODE_DEFAULT_MODEL

PROVIDER_URLS = {
    "llamacpp": "http://192.168.20.180:8081/v1/chat/completions",
    "llamacpp_2": "http://192.168.20.181:8081/v1/chat/completions",
    "opencode": OPENCODE_URL,
}

PROVIDER_DEFAULT_MODELS = {
    "llamacpp": "qwen3.5:4b",
    "llamacpp_2": "qwen3.5:4b",
    "opencode": OPENCODE_DEFAULT_MODEL,
    "local_llm": "default",
}


def create_provider(provider_type: str = "llamacpp", **kwargs) -> LLMProvider:
    ptype = (provider_type or "llamacpp").lower()
    if ptype == "opencode":
        kwargs.setdefault("base_url", PROVIDER_URLS["opencode"])
        kwargs.setdefault("model", PROVIDER_DEFAULT_MODELS["opencode"])
    elif "base_url" not in kwargs and ptype in PROVIDER_URLS:
        kwargs["base_url"] = PROVIDER_URLS[ptype]

    providers = {
        "llamacpp": LlamaCppProvider,
        "llamacpp_2": LlamaCppProvider,
        "local_llm": LocalLLMProvider,
        "opencode": OpenCodeProvider,
    }
    cls = providers.get(ptype)
    if cls is None:
        raise ValueError(
            f"Unknown provider: {provider_type}. Available: {list(providers.keys())}"
        )
    return cls(**kwargs)
