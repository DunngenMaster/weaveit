import weaviate
from weaviate.exceptions import WeaviateConnectionError
from app.core.config import get_settings


class WeaviateClient:
    """Weaviate client wrapper for connectivity checks"""
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    @property
    def client(self):
        """Lazy initialization of Weaviate client"""
        if self._client is None:
            self._client = weaviate.connect_to_local(
                host=self.settings.weaviate_url.replace("http://", "").replace("https://", "")
            )
        return self._client
    
    def check_health(self) -> bool:
        """Check if Weaviate is reachable"""
        try:
            return self.client.is_ready()
        except (WeaviateConnectionError, Exception):
            return False
    
    def close(self):
        """Close Weaviate connection"""
        if self._client:
            self._client.close()


# Global instance
weaviate_client = WeaviateClient()
