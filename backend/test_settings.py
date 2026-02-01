from app.core.config import get_settings

settings = get_settings()
print(f"Weaviate URL: {settings.weaviate_url}")
print(f"Weaviate API Key: {settings.weaviate_api_key[:20]}..." if settings.weaviate_api_key else "No API key")
print(f"Browserbase API Key: {settings.browserbase_api_key[:20]}..." if settings.browserbase_api_key else "No API key")
print(f"Browserbase Project ID: {settings.browserbase_project_id}")
