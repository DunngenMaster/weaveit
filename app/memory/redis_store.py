from typing import Dict, Optional

import redis

from app.core.config import settings


class MemoryStore:
    def __init__(self) -> None:
        self._preferences: Dict[str, Dict[str, str]] = {}
        self.redis_url = settings.redis_url
        self._client: Optional[redis.Redis] = None
        self._prefs_key = "ghost:preferences"

        try:
            client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            client.ping()
            self._client = client
        except Exception:
            self._client = None

    def _key_for_tab(self, tab_id: Optional[str]) -> str:
        if tab_id:
            return f"{self._prefs_key}:{tab_id}"
        return self._prefs_key

    def get_preferences(self, tab_id: Optional[str] = None) -> Dict[str, str]:
        key = self._key_for_tab(tab_id)
        if self._client:
            data = self._client.hgetall(key)
            return {str(k): str(v) for k, v in data.items()}
        return dict(self._preferences.get(key, {}))

    def set_preference(self, key: str, value: str, tab_id: Optional[str] = None) -> None:
        prefs_key = self._key_for_tab(tab_id)
        if self._client:
            self._client.hset(prefs_key, key, value)
            return
        if prefs_key not in self._preferences:
            self._preferences[prefs_key] = {}
        self._preferences[prefs_key][key] = value
