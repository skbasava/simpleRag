“””
Generic RAG Service Framework for LibreChat Integration
Supports multiple RAG backends through a plugin architecture
“””

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
from datetime import datetime

# FastAPI for REST API

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# For different vector store backends

try:
import chromadb
CHROMA_AVAILABLE = True
except ImportError:
CHROMA_AVAILABLE = False

try:
from pinecone import Pinecone
PINECONE_AVAILABLE = True
except ImportError:
PINECONE_AVAILABLE = False

try:
from qdrant_client import QdrantClient
QDRANT_AVAILABLE = True
except ImportError:
QDRANT_AVAILABLE = False

# ==================== Configuration Models ====================

class RAGBackendType(str, Enum):
“”“Supported RAG backend types”””
CHROMA = “chroma”
PINECONE = “pinecone”
QDRANT = “qdrant”
WEAVIATE = “weaviate”
MILVUS = “milvus”
CUSTOM = “custom”

class EmbeddingProvider(str, Enum):
“”“Supported embedding providers”””
OPENAI = “openai”
COHERE = “cohere”
HUGGINGFACE = “huggingface”
SENTENCE_TRANSFORMERS = “sentence-transformers”
CUSTOM = “custom”

@dataclass
class RAGConfig:
“”“Configuration for RAG service”””
backend_type: RAGBackendType
embedding_provider: EmbeddingProvider
embedding_model: str
collection_name: str

```
# Vector store specific configs
vector_store_config: Dict[str, Any]

# Retrieval parameters
top_k: int = 5
similarity_threshold: float = 0.7

# Chunking parameters
chunk_size: int = 512
chunk_overlap: int = 50

# Optional features
enable_reranking: bool = False
reranker_model: Optional[str] = None
enable_hyde: bool = False
enable_query_expansion: bool = False
```

# ==================== Request/Response Models ====================

class DocumentInput(BaseModel):
“”“Document to be indexed”””
id: Optional[str] = None
content: str = Field(…, description=“Document content”)
metadata: Dict[str, Any] = Field(default_factory=dict)

class QueryRequest(BaseModel):
“”“RAG query request”””
query: str = Field(…, description=“User query”)
top_k: Optional[int] = Field(None, description=“Number of results”)
filter: Optional[Dict[str, Any]] = Field(None, description=“Metadata filters”)
conversation_id: Optional[str] = None
user_id: Optional[str] = None

class RetrievedDocument(BaseModel):
“”“Retrieved document with score”””
id: str
content: str
metadata: Dict[str, Any]
score: float

class RAGResponse(BaseModel):
“”“RAG query response”””
query: str
documents: List[RetrievedDocument]
context: str
metadata: Dict[str, Any] = Field(default_factory=dict)

class IndexResponse(BaseModel):
“”“Response for indexing operations”””
success: bool
document_ids: List[str]
message: str

# ==================== Abstract Base Classes ====================

class BaseEmbeddingProvider(ABC):
“”“Abstract base class for embedding providers”””

```
@abstractmethod
def embed_text(self, text: str) -> List[float]:
    """Generate embedding for a single text"""
    pass

@abstractmethod
def embed_batch(self, texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts"""
    pass
```

class BaseVectorStore(ABC):
“”“Abstract base class for vector stores”””

```
@abstractmethod
def add_documents(self, documents: List[Dict[str, Any]], 
                 embeddings: List[List[float]]) -> List[str]:
    """Add documents with embeddings"""
    pass

@abstractmethod
def search(self, query_embedding: List[float], 
          top_k: int, filter: Optional[Dict] = None) -> List[Tuple[str, float, Dict]]:
    """Search for similar documents"""
    pass

@abstractmethod
def delete_documents(self, document_ids: List[str]) -> bool:
    """Delete documents by IDs"""
    pass

@abstractmethod
def update_document(self, document_id: str, 
                   content: str, metadata: Dict[str, Any],
                   embedding: List[float]) -> bool:
    """Update a document"""
    pass
```

class BaseReranker(ABC):
“”“Abstract base class for rerankers”””

```
@abstractmethod
def rerank(self, query: str, documents: List[Dict[str, Any]], 
          top_k: int) -> List[Dict[str, Any]]:
    """Rerank documents based on query"""
    pass
```

# ==================== Embedding Provider Implementations ====================

class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
“”“OpenAI embedding provider”””

```
def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
    try:
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)
        self.model = model
    except ImportError:
        raise ImportError("OpenAI package not installed. Run: pip install openai")

def embed_text(self, text: str) -> List[float]:
    response = self.client.embeddings.create(
        model=self.model,
        input=text
    )
    return response.data[0].embedding

def embed_batch(self, texts: List[str]) -> List[List[float]]:
    response = self.client.embeddings.create(
        model=self.model,
        input=texts
    )
    return [item.embedding for item in response.data]
```

class SentenceTransformerProvider(BaseEmbeddingProvider):
“”“Sentence Transformers embedding provider”””

```
def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
    try:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
    except ImportError:
        raise ImportError("sentence-transformers not installed. Run: pip install sentence-transformers")

def embed_text(self, text: str) -> List[float]:
    return self.model.encode(text).tolist()

def embed_batch(self, texts: List[str]) -> List[List[float]]:
    return self.model.encode(texts).tolist()
```

# ==================== Vector Store Implementations ====================

class ChromaVectorStore(BaseVectorStore):
“”“ChromaDB vector store implementation”””

```
def __init__(self, collection_name: str, persist_directory: Optional[str] = None):
    if not CHROMA_AVAILABLE:
        raise ImportError("ChromaDB not installed. Run: pip install chromadb")
    
    self.client = chromadb.PersistentClient(path=persist_directory) if persist_directory \
                 else chromadb.Client()
    self.collection = self.client.get_or_create_collection(name=collection_name)

def add_documents(self, documents: List[Dict[str, Any]], 
                 embeddings: List[List[float]]) -> List[str]:
    ids = [doc.get('id', self._generate_id(doc['content'])) for doc in documents]
    contents = [doc['content'] for doc in documents]
    metadatas = [doc.get('metadata', {}) for doc in documents]
    
    self.collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=contents,
        metadatas=metadatas
    )
    return ids

def search(self, query_embedding: List[float], 
          top_k: int, filter: Optional[Dict] = None) -> List[Tuple[str, float, Dict]]:
    results = self.collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=filter
    )
    
    documents = []
    for i in range(len(results['ids'][0])):
        documents.append((
            results['ids'][0][i],
            1 - results['distances'][0][i],  # Convert distance to similarity
            {
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i]
            }
        ))
    return documents

def delete_documents(self, document_ids: List[str]) -> bool:
    self.collection.delete(ids=document_ids)
    return True

def update_document(self, document_id: str, content: str, 
                   metadata: Dict[str, Any], embedding: List[float]) -> bool:
    self.collection.update(
        ids=[document_id],
        embeddings=[embedding],
        documents=[content],
        metadatas=[metadata]
    )
    return True

def _generate_id(self, content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()
```

class PineconeVectorStore(BaseVectorStore):
“”“Pinecone vector store implementation”””

```
def __init__(self, api_key: str, index_name: str, dimension: int = 1536):
    if not PINECONE_AVAILABLE:
        raise ImportError("Pinecone not installed. Run: pip install pinecone-client")
    
    self.pc = Pinecone(api_key=api_key)
    self.index_name = index_name
    
    # Create index if it doesn't exist
    if index_name not in self.pc.list_indexes().names():
        self.pc.create_index(
            name=index_name,
            dimension=dimension,
            metric='cosine'
        )
    
    self.index = self.pc.Index(index_name)

def add_documents(self, documents: List[Dict[str, Any]], 
                 embeddings: List[List[float]]) -> List[str]:
    vectors = []
    ids = []
    
    for doc, embedding in zip(documents, embeddings):
        doc_id = doc.get('id', self._generate_id(doc['content']))
        ids.append(doc_id)
        
        metadata = doc.get('metadata', {})
        metadata['content'] = doc['content']
        
        vectors.append({
            'id': doc_id,
            'values': embedding,
            'metadata': metadata
        })
    
    self.index.upsert(vectors=vectors)
    return ids

def search(self, query_embedding: List[float], 
          top_k: int, filter: Optional[Dict] = None) -> List[Tuple[str, float, Dict]]:
    results = self.index.query(
        vector=query_embedding,
        top_k=top_k,
        filter=filter,
        include_metadata=True
    )
    
    documents = []
    for match in results['matches']:
        content = match['metadata'].pop('content', '')
        documents.append((
            match['id'],
            match['score'],
            {
                'content': content,
                'metadata': match['metadata']
            }
        ))
    return documents

def delete_documents(self, document_ids: List[str]) -> bool:
    self.index.delete(ids=document_ids)
    return True

def update_document(self, document_id: str, content: str, 
                   metadata: Dict[str, Any], embedding: List[float]) -> bool:
    metadata['content'] = content
    self.index.upsert(vectors=[{
        'id': document_id,
        'values': embedding,
        'metadata': metadata
    }])
    return True

def _generate_id(self, content: str) -> str:
    return hashlib.md5(content.encode()).hexdigest()
```

# ==================== RAG Service Core ====================

class RAGService:
“”“Core RAG service with plugin architecture”””

```
def __init__(self, config: RAGConfig):
    self.config = config
    self.logger = logging.getLogger(__name__)
    
    # Initialize embedding provider
    self.embedding_provider = self._initialize_embedding_provider()
    
    # Initialize vector store
    self.vector_store = self._initialize_vector_store()
    
    # Initialize reranker if enabled
    self.reranker = self._initialize_reranker() if config.enable_reranking else None

def _initialize_embedding_provider(self) -> BaseEmbeddingProvider:
    """Initialize the embedding provider based on config"""
    provider_type = self.config.embedding_provider
    
    if provider_type == EmbeddingProvider.OPENAI:
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        return OpenAIEmbeddingProvider(api_key, self.config.embedding_model)
    
    elif provider_type == EmbeddingProvider.SENTENCE_TRANSFORMERS:
        return SentenceTransformerProvider(self.config.embedding_model)
    
    else:
        raise ValueError(f"Unsupported embedding provider: {provider_type}")

def _initialize_vector_store(self) -> BaseVectorStore:
    """Initialize the vector store based on config"""
    backend_type = self.config.backend_type
    store_config = self.config.vector_store_config
    
    if backend_type == RAGBackendType.CHROMA:
        return ChromaVectorStore(
            collection_name=self.config.collection_name,
            persist_directory=store_config.get('persist_directory')
        )
    
    elif backend_type == RAGBackendType.PINECONE:
        return PineconeVectorStore(
            api_key=store_config['api_key'],
            index_name=self.config.collection_name,
            dimension=store_config.get('dimension', 1536)
        )
    
    else:
        raise ValueError(f"Unsupported backend: {backend_type}")

def _initialize_reranker(self) -> Optional[BaseReranker]:
    """Initialize reranker if configured"""
    # Placeholder for reranker implementation
    return None

def _chunk_text(self, text: str) -> List[str]:
    """Split text into chunks"""
    chunks = []
    chunk_size = self.config.chunk_size
    overlap = self.config.chunk_overlap
    
    for i in range(0, len(text), chunk_size - overlap):
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks

def index_documents(self, documents: List[DocumentInput]) -> IndexResponse:
    """Index documents into the vector store"""
    try:
        all_chunks = []
        all_doc_ids = []
        
        for doc in documents:
            # Chunk the document
            chunks = self._chunk_text(doc.content)
            
            for i, chunk in enumerate(chunks):
                chunk_id = doc.id or self._generate_doc_id(doc.content)
                chunk_id = f"{chunk_id}_chunk_{i}"
                
                all_chunks.append({
                    'id': chunk_id,
                    'content': chunk,
                    'metadata': {
                        **doc.metadata,
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'indexed_at': datetime.utcnow().isoformat()
                    }
                })
                all_doc_ids.append(chunk_id)
        
        # Generate embeddings
        contents = [chunk['content'] for chunk in all_chunks]
        embeddings = self.embedding_provider.embed_batch(contents)
        
        # Store in vector database
        stored_ids = self.vector_store.add_documents(all_chunks, embeddings)
        
        return IndexResponse(
            success=True,
            document_ids=stored_ids,
            message=f"Successfully indexed {len(documents)} documents ({len(stored_ids)} chunks)"
        )
    
    except Exception as e:
        self.logger.error(f"Error indexing documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def query(self, request: QueryRequest) -> RAGResponse:
    """Query the RAG system"""
    try:
        # Generate query embedding
        query_embedding = self.embedding_provider.embed_text(request.query)
        
        # Retrieve documents
        top_k = request.top_k or self.config.top_k
        results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            filter=request.filter
        )
        
        # Filter by similarity threshold
        filtered_results = [
            (doc_id, score, data) for doc_id, score, data in results
            if score >= self.config.similarity_threshold
        ]
        
        # Rerank if enabled
        if self.reranker and filtered_results:
            # Reranking logic would go here
            pass
        
        # Format response
        documents = [
            RetrievedDocument(
                id=doc_id,
                content=data['content'],
                metadata=data['metadata'],
                score=score
            )
            for doc_id, score, data in filtered_results
        ]
        
        # Create context from retrieved documents
        context = "\n\n".join([
            f"[Document {i+1}] {doc.content}"
            for i, doc in enumerate(documents)
        ])
        
        return RAGResponse(
            query=request.query,
            documents=documents,
            context=context,
            metadata={
                'total_results': len(documents),
                'retrieval_time': datetime.utcnow().isoformat()
            }
        )
    
    except Exception as e:
        self.logger.error(f"Error querying RAG: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def _generate_doc_id(self, content: str) -> str:
    """Generate unique document ID"""
    return hashlib.md5(content.encode()).hexdigest()
```

# ==================== FastAPI Application ====================

class RAGServiceAPI:
“”“FastAPI application for RAG service”””

```
def __init__(self, rag_service: RAGService):
    self.app = FastAPI(
        title="Generic RAG Service for LibreChat",
        description="Plugin-based RAG service supporting multiple backends",
        version="1.0.0"
    )
    self.rag_service = rag_service
    self._setup_middleware()
    self._setup_routes()

def _setup_middleware(self):
    """Setup CORS and other middleware"""
    self.app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

def _verify_api_key(self, x_api_key: Optional[str] = Header(None)):
    """Verify API key if configured"""
    expected_key = os.getenv('RAG_API_KEY')
    if expected_key and x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

def _setup_routes(self):
    """Setup API routes"""
    
    @self.app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    @self.app.post("/index", response_model=IndexResponse)
    async def index_documents(
        documents: List[DocumentInput],
        api_key: str = Depends(self._verify_api_key)
    ):
        """Index documents into the RAG system"""
        return self.rag_service.index_documents(documents)
    
    @self.app.post("/query", response_model=RAGResponse)
    async def query_rag(
        request: QueryRequest,
        api_key: str = Depends(self._verify_api_key)
    ):
        """Query the RAG system"""
        return self.rag_service.query(request)
    
    @self.app.delete("/documents/{document_id}")
    async def delete_document(
        document_id: str,
        api_key: str = Depends(self._verify_api_key)
    ):
        """Delete a document"""
        success = self.rag_service.vector_store.delete_documents([document_id])
        return {"success": success, "document_id": document_id}
    
    @self.app.get("/config")
    async def get_config(api_key: str = Depends(self._verify_api_key)):
        """Get current RAG configuration"""
        return {
            "backend_type": self.rag_service.config.backend_type,
            "embedding_provider": self.rag_service.config.embedding_provider,
            "collection_name": self.rag_service.config.collection_name,
            "top_k": self.rag_service.config.top_k,
            "similarity_threshold": self.rag_service.config.similarity_threshold
        }
```

# ==================== Main Application ====================

def create_app(config: RAGConfig) -> FastAPI:
“”“Create and configure the RAG service application”””

```
# Initialize RAG service
rag_service = RAGService(config)

# Create FastAPI app
api = RAGServiceAPI(rag_service)

return api.app
```

# ==================== Example Usage ====================

if **name** == “**main**”:
# Configure logging
logging.basicConfig(
level=logging.INFO,
format=’%(asctime)s - %(name)s - %(levelname)s - %(message)s’
)

```
# Example configuration for ChromaDB with OpenAI embeddings
config = RAGConfig(
    backend_type=RAGBackendType.CHROMA,
    embedding_provider=EmbeddingProvider.SENTENCE_TRANSFORMERS,
    embedding_model="all-MiniLM-L6-v2",
    collection_name="librechat_docs",
    vector_store_config={
        "persist_directory": "./chroma_db"
    },
    top_k=5,
    similarity_threshold=0.7,
    chunk_size=512,
    chunk_overlap=50,
    enable_reranking=False
)

# Create application
app = create_app(config)

# Run server
print("Starting RAG Service on http://0.0.0.0:8000")
print("API Documentation available at http://0.0.0.0:8000/docs")

uvicorn.run(app, host="0.0.0.0", port=8000)
```