import redis
from redis.exceptions import ConnectionError, TimeoutError
from app.core.config import get_settings


class RedisClient:
    """Redis client wrapper for connectivity checks"""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of Redis client"""
        if self._client is None:
            self._client = redis.from_url(
                self.settings.redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2
            )
        return self._client
    
    def check_health(self) -> bool:
        """Check if Redis is reachable"""
        try:
            return self.client.ping()
        except (ConnectionError, TimeoutError, Exception):
            return False
    
    def close(self):
        """Close Redis connection"""
        if self._client:
            self._client.close()


# Global instance
redis_client = RedisClient()
