"""LLM client factory — supports Gemini and Groq via LangChain."""

from langchain_core.language_models.chat_models import BaseChatModel
from src.config import settings


def get_llm(
    provider: str | None = None,
    model: str | None = None,
    temperature: float = 0.2,
) -> BaseChatModel:
    """
    Create and return an LLM client based on configuration.

    Args:
        provider: Override the default LLM_PROVIDER from settings.
        model: Override the default LLM_MODEL from settings.
        temperature: Sampling temperature.

    Returns:
        A LangChain chat model instance.

    Raises:
        ValueError: If the provider is unknown or API key is missing.
    """
    provider = (provider or settings.LLM_PROVIDER).lower()
    model = model or settings.LLM_MODEL

    if provider == "gemini":
        if not settings.GEMINI_API_KEY:
            raise ValueError(
                "AFTERBURNER_GEMINI_API_KEY is required when LLM_PROVIDER='gemini'. "
                "Set it in your .env file."
            )
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=temperature,
        )

    elif provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "AFTERBURNER_GROQ_API_KEY is required when LLM_PROVIDER='groq'. "
                "Set it in your .env file."
            )
        from langchain_groq import ChatGroq

        return ChatGroq(
            model=model,
            groq_api_key=settings.GROQ_API_KEY,
            temperature=temperature,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. Supported: 'gemini', 'groq'."
        )
