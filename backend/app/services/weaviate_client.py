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
            # Sprint 17.6: SkillMemory collection with quality scoring
            if not self.client.collections.exists("SkillMemory"):
                self.client.collections.create(
                    name="SkillMemory",
                    properties=[
                        wvc.config.Property(name="user_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="domain", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="pattern", data_type=wvc.config.DataType.TEXT),  # The learned pattern/instruction
                        wvc.config.Property(name="context", data_type=wvc.config.DataType.TEXT),  # When to apply it
                        wvc.config.Property(name="tags", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="reward", data_type=wvc.config.DataType.NUMBER),  # Reward score
                        wvc.config.Property(name="critic_score", data_type=wvc.config.DataType.NUMBER),  # Critic score
                        wvc.config.Property(name="quality", data_type=wvc.config.DataType.NUMBER),  # reward * critic_score
                        wvc.config.Property(name="source_attempt_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="status", data_type=wvc.config.DataType.TEXT),  # active/superseded
                        wvc.config.Property(name="created_at", data_type=wvc.config.DataType.DATE),
                    ]
                )

            # Sprint 17.9: ArtifactSummary collection for clean browsing data
            if not self.client.collections.exists("ArtifactSummary"):
                self.client.collections.create(
                    name="ArtifactSummary",
                    properties=[
                        wvc.config.Property(name="user_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="kind", data_type=wvc.config.DataType.TEXT),  # job_posting, article, etc.
                        wvc.config.Property(name="title", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="company", data_type=wvc.config.DataType.TEXT),  # For job_posting
                        wvc.config.Property(name="location", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="skills", data_type=wvc.config.DataType.TEXT_ARRAY),
                        wvc.config.Property(name="summary_bullets", data_type=wvc.config.DataType.TEXT_ARRAY),  # 5-7 bullet points
                        wvc.config.Property(name="source_url", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="raw_html_key", data_type=wvc.config.DataType.TEXT),  # Redis key for raw HTML
                        wvc.config.Property(name="extraction_method", data_type=wvc.config.DataType.TEXT),  # dom/heuristics/screenshot
                        wvc.config.Property(name="created_at", data_type=wvc.config.DataType.DATE),
                    ]
                )

            # Run-level memory collection for agent orchestration
            if not self.client.collections.exists("RunMemory"):
                self.client.collections.create(
                    name="RunMemory",
                    properties=[
                        wvc.config.Property(name="run_id", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="goal", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="query", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="summary_text", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="policy_json", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="prompt_delta_json", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="patch_json", data_type=wvc.config.DataType.TEXT),
                        wvc.config.Property(name="metrics_json", data_type=wvc.config.DataType.TEXT),
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

    def search_run_memory(self, text: str, limit: int = 3) -> list[dict]:
        try:
            if not self.client.is_ready():
                return []
            if not self.client.collections.exists("RunMemory"):
                return []
            collection = self.client.collections.get("RunMemory")
            results = collection.query.bm25(
                query=text,
                limit=limit
            )
            items = []
            for obj in results.objects:
                props = obj.properties or {}
                items.append(props)
            return items
        except Exception as e:
            print(f"Error searching RunMemory: {e}")
            return []


weaviate_client = WeaviateClient()
