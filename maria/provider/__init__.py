from maria.provider.base import LLMProvider
from maria.provider.llamacpp import LlamaCppProvider
from maria.provider.local_llm import LocalLLMProvider


def create_provider(provider_type: str = "llamacpp", **kwargs) -> LLMProvider:
    providers = {
        "llamacpp": LlamaCppProvider,
        "local_llm": LocalLLMProvider,
    }
    cls = providers.get(provider_type.lower())
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    return cls(**kwargs)
