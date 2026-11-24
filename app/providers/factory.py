from collections.abc import Callable

from pydantic import SecretStr

from app.core.config import Settings
from app.providers.base import ManagedAIProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider


def create_provider(settings: Settings) -> ManagedAIProvider | None:
    """Only the selected provider is constructed; credentials never leave the backend."""
    if settings.ai_provider == "unconfigured":
        return None
    providers: dict[str, tuple[SecretStr | None, Callable[[Settings], ManagedAIProvider]]] = {
        "openai": (settings.openai_api_key, OpenAIProvider),
        "gemini": (settings.gemini_api_key, GeminiProvider),
    }
    key, adapter = providers[settings.ai_provider]
    return adapter(settings) if key is not None else None
