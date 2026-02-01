from typing import Dict, Optional

import redis

from app.core.config import settings


class MemoryStore:
    def __init__(self) -> None:
        self._preferences: Dict[str, str] = {}
        self.redis_url = settings.redis_url
        self._client: Optional[redis.Redis] = None
        self._prefs_key = "ghost:preferences"

        try:
            client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._client = client
        except Exception:
            self._client = None

    def get_preferences(self) -> Dict[str, str]:
        if self._client:
            data = self._client.hgetall(self._prefs_key)
            return {str(k): str(v) for k, v in data.items()}
        return dict(self._preferences)

    def set_preference(self, key: str, value: str) -> None:
        if self._client:
            self._client.hset(self._prefs_key, key, value)
            return
        self._preferences[key] = value
