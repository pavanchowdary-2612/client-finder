import os
import streamlit as st

from ..core.settings import settings


def render_sidebar() -> dict:
    """Load and return workspace configuration directly from environment settings without rendering sidebar UI."""
    search_provider = "tavily" if settings.tavily_api_key else ("brave" if settings.brave_search_api_key else "tavily")
    search_key = settings.tavily_api_key if search_provider == "tavily" else settings.brave_search_api_key

    if settings.groq_api_key:
        llm_provider = "groq"
        llm_key = settings.groq_api_key
        model = settings.groq_model
    elif settings.openai_api_key:
        llm_provider = "openai"
        llm_key = settings.openai_api_key
        model = settings.openai_model
    else:
        llm_provider = "template only"
        llm_key = ""
        model = ""

    return {
        "search_provider": search_provider,
        "search_key": search_key,
        "llm_provider": llm_provider,
        "llm_key": llm_key,
        "model": model,
        "sender_name": os.getenv("SENDER_NAME", ""),
        "business_name": os.getenv("SENDER_BUSINESS", ""),
        "sender_email": os.getenv("SENDER_EMAIL", ""),
        "sender_address": os.getenv("SENDER_POSTAL_ADDRESS", ""),
    }

