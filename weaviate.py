import weaviate
import os
import uuid


class WeaviateDriver:
    def __init__(self):
        self.client = weaviate.Client(
            url=os.environ["WEAVIATE_URL"]
        )
        self.collection = self.client.collections.get("AccessControlPolicy")

    def insert_vector(self, vector, properties) -> str:
        wid = str(uuid.uuid4())
        self.collection.data.insert(
            uuid=wid,
            vector=vector,
            properties=properties,
        )
        return wid

    def semantic_search(self, vector, filters=None, limit=10):
        return self.collection.query.near_vector(
            near_vector=vector,
            limit=limit,
            filters=filters,
        )