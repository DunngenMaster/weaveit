from langchain_google_genai import ChatGoogleGenerativeAI
from app.core.config import get_settings


def get_chat_model():
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        temperature=0.3,
        google_api_key=settings.gemini_api_key
    )
