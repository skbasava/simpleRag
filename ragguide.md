# Generic RAG Service Framework - Complete Setup Guide

## 📋 Table of Contents

1. [Overview](#overview)
1. [Quick Start](#quick-start)
1. [Installation](#installation)
1. [Configuration](#configuration)
1. [LibreChat Integration](#librechat-integration)
1. [Testing](#testing)
1. [Production Deployment](#production-deployment)
1. [API Reference](#api-reference)

-----

## Overview

This framework provides a **generic, plugin-based RAG service** that:

- ✅ Integrates seamlessly with LibreChat
- ✅ Supports multiple vector databases (ChromaDB, Pinecone, Qdrant, Weaviate, Milvus)
- ✅ Supports multiple embedding providers (OpenAI, Cohere, HuggingFace, Sentence Transformers)
- ✅ Provides REST API for easy integration
- ✅ Includes document loaders and CLI tools
- ✅ Implements security guardrails

-----

## Quick Start

### Option 1: Local Development (ChromaDB + Sentence Transformers)

```bash
# 1. Clone the repository
git clone <your-repo>
cd rag-service

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export RAG_API_KEY=your-secure-key
export RAG_BACKEND=chroma
export EMBEDDING_PROVIDER=sentence-transformers

# 4. Start the service
python rag_service.py

# 5. Test the service
curl http://localhost:8000/health
```

### Option 2: Docker Deployment

```bash
# 1. Create .env file with your configuration
cat > .env << EOF
RAG_API_KEY=your-secure-key
RAG_BACKEND=chroma
EMBEDDING_PROVIDER=sentence-transformers
EMBEDDING_MODEL=all-MiniLM-L6-v2
EOF

# 2. Start with Docker Compose
docker-compose -f docker-compose.rag.yml up -d

# 3. Verify services are running
docker-compose ps
```

-----

## Installation

### Prerequisites

- Python 3.9+
- pip or conda
- Docker (optional, for containerized deployment)

### Step 1: Install Core Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install base requirements
pip install fastapi uvicorn pydantic python-multipart
```

### Step 2: Install Vector Store Backend

Choose one or more:

```bash
# ChromaDB (local, free)
pip install chromadb

# Pinecone (cloud, managed)
pip install pinecone-client

# Qdrant (self-hosted or cloud)
pip install qdrant-client

# Weaviate (self-hosted or cloud)
pip install weaviate-client

# Milvus (self-hosted or cloud)
pip install pymilvus
```

### Step 3: Install Embedding Provider

Choose one or more:

```bash
# OpenAI
pip install openai

# Sentence Transformers (local, free)
pip install sentence-transformers torch

# Cohere
pip install cohere

# HuggingFace
pip install transformers torch
```

### Step 4: Install Utilities

```bash
pip install requests python-dotenv sqlparse
```

-----

## Configuration

### Configuration File Structure

Create `config.json`:

```json
{
  "backend_type": "chroma",
  "embedding_provider": "sentence-transformers",
  "embedding_model": "all-MiniLM-L6-v2",
  "collection_name": "librechat_docs",
  "vector_store_config": {
    "persist_directory": "./chroma_db"
  },
  "top_k": 5,
  "similarity_threshold": 0.7,
  "chunk_size": 512,
  "chunk_overlap": 50,
  "enable_reranking": false,
  "enable_hyde": false,
  "enable_query_expansion": false
}
```

### Configuration Options

#### Backend Types

- `chroma`: Local, persistent, free
- `pinecone`: Cloud, managed, paid
- `qdrant`: Self-hosted or cloud
- `weaviate`: Self-hosted or cloud
- `milvus`: Self-hosted or cloud

#### Embedding Providers

- `openai`: High quality, paid (e.g., text-embedding-3-small)
- `sentence-transformers`: Local, free (e.g., all-MiniLM-L6-v2)
- `cohere`: Cloud, paid (e.g., embed-english-v3.0)
- `huggingface`: Various models, local or API

#### Retrieval Parameters

- `top_k`: Number of documents to retrieve (1-20)
- `similarity_threshold`: Minimum similarity score (0.0-1.0)
- `chunk_size`: Document chunk size in characters
- `chunk_overlap`: Overlap between chunks

-----

## LibreChat Integration

### Step 1: Configure LibreChat

Edit `librechat.yaml`:

```yaml
endpoints:
  custom:
    - name: "RAG-Enhanced Chat"
      apiKey: "${RAG_API_KEY}"
      baseURL: "http://localhost:8000"
      models:
        default:
          - "rag-assistant"
      titleConvo: true
      modelDisplayLabel: "RAG Service"
```

### Step 2: Start Services

```bash
# Start RAG service
python rag_service.py

# In another terminal, start LibreChat
cd librechat
npm start
```

### Step 3: Index Documents

```bash
# Using CLI
python rag_client.py index --dir ./documents

# Using Python
from rag_client import RAGClient, DocumentLoader

client = RAGClient("http://localhost:8000", api_key="your-key")
loader = DocumentLoader(client)
loader.load_directory("./documents")
```

### Step 4: Test in LibreChat

1. Open LibreChat at http://localhost:3080
1. Select “RAG-Enhanced Chat” model
1. Ask questions about your indexed documents
1. The RAG service will automatically augment queries with relevant context

-----

## Testing

### Unit Tests

Create `test_rag_service.py`:

```python
import pytest
from rag_service import RAGService, RAGConfig, RAGBackendType, EmbeddingProvider

@pytest.fixture
def rag_service():
    config = RAGConfig(
        backend_type=RAGBackendType.CHROMA,
        embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
        embedding_model="all-MiniLM-L6-v2",
        collection_name="test_collection",
        vector_store_config={"persist_directory": "./test_db"}
    )
    return RAGService(config)

def test_index_document(rag_service):
    documents = [
        {"content": "Python is a programming language.", "metadata": {}}
    ]
    result = rag_service.index_documents(documents)
    assert result.success
    assert len(result.document_ids) > 0

def test_query(rag_service):
    # First index a document
    documents = [{"content": "Python is great for data science.", "metadata": {}}]
    rag_service.index_documents(documents)
    
    # Then query
    from rag_service import QueryRequest
    request = QueryRequest(query="What is Python used for?")
    response = rag_service.query(request)
    
    assert len(response.documents) > 0
    assert response.documents[0].score > 0.5
```

Run tests:

```bash
pytest test_rag_service.py -v
```

### Integration Tests

```bash
# Test API endpoints
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '[{"content": "Test document", "metadata": {}}]'

curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-key" \
  -d '{"query": "test", "top_k": 5}'
```

### Performance Testing

```python
import time
from rag_client import RAGClient

client = RAGClient("http://localhost:8000", api_key="your-key")

# Test indexing performance
start = time.time()
documents = [{"content": f"Document {i}", "metadata": {}} for i in range(100)]
result = client.index_documents(documents)
print(f"Indexed 100 docs in {time.time() - start:.2f}s")

# Test query performance
start = time.time()
for i in range(10):
    client.query(f"Query {i}")
print(f"10 queries in {time.time() - start:.2f}s")
```

-----

## Production Deployment

### Docker Compose (Recommended)

Full stack with monitoring:

```yaml
version: '3.8'

services:
  rag-service:
    build: ./rag-service
    environment:
      - RAG_API_KEY=${RAG_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    ports:
      - "8000:8000"
    volumes:
      - rag-data:/app/data
    restart: always
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  librechat:
    image: librechat/librechat:latest
    depends_on:
      - rag-service
      - mongodb
    ports:
      - "3080:3080"
    environment:
      - MONGO_URI=mongodb://mongodb:27017/LibreChat
      - RAG_SERVICE_URL=http://rag-service:8000
    restart: always

  mongodb:
    image: mongo:latest
    volumes:
      - mongodb-data:/data/db
    restart: always

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
    depends_on:
      - librechat
    restart: always

volumes:
  rag-data:
  mongodb-data:
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: rag-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: rag-service
  template:
    metadata:
      labels:
        app: rag-service
    spec:
      containers:
      - name: rag-service
        image: your-registry/rag-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: RAG_API_KEY
          valueFrom:
            secretKeyRef:
              name: rag-secrets
              key: api-key
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
---
apiVersion: v1
kind: Service
metadata:
  name: rag-service
spec:
  selector:
    app: rag-service
  ports:
  - port: 8000
    targetPort: 8000
  type: LoadBalancer
```

### Environment Variables for Production

```bash
# Security
RAG_API_KEY=<strong-random-key>
ALLOWED_ORIGINS=https://your-domain.com

# Vector Store
RAG_BACKEND=pinecone  # Use managed service in production
PINECONE_API_KEY=<your-key>
PINECONE_ENVIRONMENT=us-east-1

# Embeddings
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=<your-key>

# Performance
MAX_WORKERS=4
CACHE_ENABLED=true
CACHE_TTL=3600

# Monitoring
LOG_LEVEL=INFO
SENTRY_DSN=<your-sentry-dsn>
```

-----

## API Reference

### Endpoints

#### Health Check

```
GET /health
```

Response:

```json
{
  "status": "healthy",
  "timestamp": "2025-01-15T10:30:00Z"
}
```

#### Index Documents

```
POST /index
Headers: X-API-Key: your-key
```

Request:

```json
[
  {
    "id": "doc_1",
    "content": "Document content",
    "metadata": {"author": "John", "date": "2025-01-15"}
  }
]
```

Response:

```json
{
  "success": true,
  "document_ids": ["doc_1_chunk_0", "doc_1_chunk_1"],
  "message": "Successfully indexed 1 documents (2 chunks)"
}
```

#### Query

```
POST /query
Headers: X-API-Key: your-key
```

Request:

```json
{
  "query": "What is Python?",
  "top_k": 5,
  "filter": {"author": "John"},
  "conversation_id": "conv_123"
}
```

Response:

```json
{
  "query": "What is Python?",
  "documents": [
    {
      "id": "doc_1_chunk_0",
      "content": "Python is a programming language...",
      "metadata": {"author": "John"},
      "score": 0.89
    }
  ],
  "context": "[Document 1] Python is a programming language...",
  "metadata": {
    "total_results": 1,
    "retrieval_time": "2025-01-15T10:31:00Z"
  }
}
```

#### Delete Document

```
DELETE /documents/{document_id}
Headers: X-API-Key: your-key
```

Response:

```json
{
  "success": true,
  "document_id": "doc_1"
}
```

#### Get Configuration

```
GET /config
Headers: X-API-Key: your-key
```

Response:

```json
{
  "backend_type": "chroma",
  "embedding_provider": "sentence-transformers",
  "collection_name": "librechat_docs",
  "top_k": 5,
  "similarity_threshold": 0.7
}
```

-----

## Troubleshooting

### Common Issues

**Issue: Service won’t start**

```bash
# Check logs
docker-compose logs rag-service

# Verify dependencies
pip list | grep -E "fastapi|chromadb|sentence"
```

**Issue: Low retrieval quality**

```python
# Adjust similarity threshold
config.similarity_threshold = 0.6  # Lower = more results

# Increase top_k
config.top_k = 10

# Try different embedding model
config.embedding_model = "all-mpnet-base-v2"  # Higher quality
```

**Issue: Out of memory**

```bash
# Reduce batch size
config.chunk_size = 256

# Use smaller embedding model
config.embedding_model = "all-MiniLM-L6-v2"
```

-----

## Advanced Features

### Custom Vector Store

Implement your own vector store:

```python
from rag_service import BaseVectorStore

class MyCustomVectorStore(BaseVectorStore):
    def __init__(self, config):
        # Your initialization
        pass
    
    def add_documents(self, documents, embeddings):
        # Your implementation
        pass
    
    def search(self, query_embedding, top_k, filter=None):
        # Your implementation
        pass
```

### Custom Embedding Provider

```python
from rag_service import BaseEmbeddingProvider

class MyEmbeddingProvider(BaseEmbeddingProvider):
    def embed_text(self, text):
        # Your implementation
        return embedding_vector
    
    def embed_batch(self, texts):
        # Your implementation
        return embedding_vectors
```

-----

## Support & Contributing

For issues, questions, or contributions:

- GitHub Issues: [your-repo/issues]
- Documentation: [your-docs-url]
- Discord: [your-discord]

## License

MIT License - see LICENSE file for details