import redis
from redis.exceptions import ConnectionError, TimeoutError
from app.core.config import get_settings


class RedisClient:
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            redis_url = self.settings.redis_url
            if redis_url.startswith("rediss://"):
                self._client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    ssl_cert_reqs=None
                )
            else:
                self._client = redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
        return self._client
    
    def check_health(self) -> bool:
        try:
            return self.client.ping()
        except (ConnectionError, TimeoutError, Exception):
            return False
    
    def close(self):
        if self._client:
            self._client.close()
    
    def get_client(self):
        return self.client


redis_client = RedisClient()
