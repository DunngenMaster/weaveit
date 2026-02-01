import weaviate
import weaviate.classes as wvc
from app.core.config import get_settings

settings = get_settings()

c = weaviate.connect_to_weaviate_cloud(
    cluster_url=settings.weaviate_url,
    auth_credentials=weaviate.auth.AuthApiKey(settings.weaviate_api_key)
)

col = c.collections.get('MemoryItem')
results = col.query.fetch_objects(
    filters=wvc.query.Filter.by_property('user_id').equal('user_test'),
    limit=10
)

print(f'\nFound {len(results.objects)} memories for user_test:\n')
for obj in results.objects:
    props = obj.properties
    print(f"Kind: {props['kind']}")
    print(f"Key: {props['key']}")
    print(f"Text: {props['text']}")
    print(f"Confidence: {props['confidence']}")
    print(f"Tags: {props['tags']}")
    print(f"Status: {props['status']}")
    print('-' * 60)

c.close()
