import weaviate
import weaviate.classes as wvc
from weaviate.exceptions import WeaviateConnectionError
from app.core.config import get_settings


class WeaviateClient:
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            if self.settings.weaviate_api_key:
                self._client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=self.settings.weaviate_url,
                    auth_credentials=weaviate.auth.AuthApiKey(self.settings.weaviate_api_key)
                )
            else:
                self._client = weaviate.connect_to_local(
                    host=self.settings.weaviate_url.replace("http://", "").replace("https://", "")
                )
        return self._client
    
    def check_health(self) -> bool:
        try:
            return self.client.is_ready()
        except (WeaviateConnectionError, Exception):
            return False
    
    def create_schema(self):
        try:
            if not self.client.is_ready():
                return False
            
            if not self.client.collections.exists("MemoryItem"):
                self.client.collections.create(
                    name="MemoryItem",
                    properties=[
                        wvc.config.Property(name="user_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="kind", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="key", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="text", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="source", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="source_url", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="confidence", data_type=wvc.config.DataType.NUMBER),
                        wvc.config.Property(name="status", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="created_at", data_type=wvc.config.DataType.DATE),
                        wvc.config.Property(name="last_seen_at", data_type=wvc.config.DataType.DATE),
                    ]
                )
            
            if not self.client.collections.exists("RunTrace"):
                self.client.collections.create(
                    name="RunTrace",
                    properties=[
                        wvc.config.Property(name="run_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="tab_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="goal", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="query", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="status", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="trace_json", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="created_at", data_type=wvc.config.DataType.DATE),
                    ]
                )
            
            if not self.client.collections.exists("RunFeedback"):
                self.client.collections.create(
                    name="RunFeedback",
                    properties=[
                        wvc.config.Property(name="run_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="tab_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="notes", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="created_at", data_type=wvc.config.DataType.DATE),
                    ]
                )
            return True
        except Exception as e:
            print(f"Error creating schema: {e}")
            return False
    
    def close(self):
        if self._client:
            self._client.close()


weaviate_client = WeaviateClient()
