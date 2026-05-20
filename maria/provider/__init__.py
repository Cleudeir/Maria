from maria.provider.base import LLMProvider
from maria.provider.ollama import OllamaProvider
from maria.provider.opencode import OpenCodeProvider


def create_provider(provider_type: str = "ollama", **kwargs) -> LLMProvider:
    providers = {
        "ollama": OllamaProvider,
        "opencode": OpenCodeProvider,
    }
    cls = providers.get(provider_type.lower())
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_type}. Available: {list(providers.keys())}")
    return cls(**kwargs)
