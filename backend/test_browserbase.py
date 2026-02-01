import httpx
from app.core.config import get_settings

settings = get_settings()

print(f"Browserbase API Key: {settings.browserbase_api_key[:20]}...")
print(f"Making test request...")

headers = {
    "Authorization": f"Bearer {settings.browserbase_api_key}",
    "Content-Type": "application/json"
}

print(f"\nTrying with Authorization header...")
print(f"Headers: {headers}")

try:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            "https://api.browserbase.com/v1/sessions",
            headers=headers,
            json={"metadata": {"user_id": "test"}}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
