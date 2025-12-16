from weaviate.classes.config import (
    Configure, Property, DataType, Tokenization, VectorDistances
)

CLASS_NAME = "AccessControlPolicy"


def ensure_schema(client):
    if client.collections.exists(CLASS_NAME):
        return

    client.collections.create(
        name=CLASS_NAME,
        description="Policy chunks for semantic retrieval",
        vectorizer_config=Configure.Vectorizer.none(),
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE
        ),
        properties=[
            Property("chunk_id", DataType.INT),
            Property("project", DataType.TEXT, tokenization=Tokenization.FIELD),
            Property("version", DataType.TEXT, tokenization=Tokenization.FIELD),
            Property("mpu_name", DataType.TEXT, tokenization=Tokenization.FIELD),
            Property("profile", DataType.TEXT, tokenization=Tokenization.FIELD),
            Property("rg_index", DataType.INT),
            Property("chunk_text", DataType.TEXT, tokenization=Tokenization.WORD),
        ],
    )