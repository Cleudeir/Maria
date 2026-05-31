from maria.provider.base import LLMProvider
from maria.provider.llamacpp import LlamaCppProvider
from maria.provider.local_llm import LocalLLMProvider

PROVIDER_URLS = {
    "llamacpp": "http://192.168.20.180:8081/v1/chat/completions",
    "llamacpp_2": "http://192.168.20.181:8081/v1/chat/completions",
}


def create_provider(provider_type: str = "llamacpp", **kwargs) -> LLMProvider:
    if "base_url" not in kwargs and provider_type in PROVIDER_URLS:
        kwargs["base_url"] = PROVIDER_URLS[provider_type]

    providers = {
        "llamacpp": LlamaCppProvider,
        "llamacpp_2": LlamaCppProvider,
        "local_llm": LocalLLMProvider,
    }
    cls = providers.get(provider_type.lower())
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    return cls(**kwargs)
