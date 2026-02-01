from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    browserbase_api_key: str = ""
    
    class Config:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        case_sensitive = False

settings = Settings()
print(f"Direct load - Browserbase key: {settings.browserbase_api_key}")
print(f"Key length: {len(settings.browserbase_api_key)}")

# Also check env file directly
env_path = os.path.join(os.path.dirname(__file__), ".env")
print(f"\nEnv file path: {env_path}")
print(f"File exists: {os.path.exists(env_path)}")

with open(env_path, 'r') as f:
    lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if 'BROWSERBASE' in line:
            print(f"Line {i}: {repr(line)}")
