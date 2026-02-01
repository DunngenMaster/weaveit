import weaviate
import weaviate.classes as wvc

c = weaviate.connect_to_weaviate_cloud(
    cluster_url='https://a5loitqjsfm3mejfr6yfoq.c0.us-west3.gcp.weaviate.cloud',
    auth_credentials=weaviate.auth.AuthApiKey('enJCekZ3UVM3Wk45ZnltRl85ZUh6RTRSNWtiMDFCZVJsT05Teld2RjRZdTg3MlpZYjVZc3o1c1JMQTFVPV92MjAw')
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
