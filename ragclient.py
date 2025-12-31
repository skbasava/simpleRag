“””
RAG Service Client Library and Integration Helpers
Provides easy integration with LibreChat and other applications
“””

import os
import json
import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

# ==================== Client Library ====================

class RAGClient:
“”“Client for interacting with the RAG service”””

```
def __init__(self, base_url: str, api_key: Optional[str] = None):
    """
    Initialize RAG client
    
    Args:
        base_url: Base URL of the RAG service
        api_key: Optional API key for authentication
    """
    self.base_url = base_url.rstrip('/')
    self.api_key = api_key or os.getenv('RAG_API_KEY')
    self.session = requests.Session()
    
    if self.api_key:
        self.session.headers.update({'X-API-Key': self.api_key})
    
    self.logger = logging.getLogger(__name__)

def health_check(self) -> Dict[str, Any]:
    """Check service health"""
    try:
        response = self.session.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        self.logger.error(f"Health check failed: {str(e)}")
        raise

def index_document(self, content: str, 
                   metadata: Optional[Dict[str, Any]] = None,
                   doc_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Index a single document
    
    Args:
        content: Document content
        metadata: Optional metadata
        doc_id: Optional document ID
        
    Returns:
        Response with document IDs
    """
    documents = [{
        'content': content,
        'metadata': metadata or {},
        'id': doc_id
    }]
    return self.index_documents(documents)

def index_documents(self, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Index multiple documents
    
    Args:
        documents: List of documents with content and metadata
        
    Returns:
        Response with document IDs
    """
    try:
        response = self.session.post(
            f"{self.base_url}/index",
            json=documents
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        self.logger.error(f"Indexing failed: {str(e)}")
        raise

def query(self, query: str, 
          top_k: Optional[int] = None,
          filter: Optional[Dict[str, Any]] = None,
          conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Query the RAG system
    
    Args:
        query: User query
        top_k: Number of results to return
        filter: Optional metadata filters
        conversation_id: Optional conversation ID for context
        
    Returns:
        Query response with retrieved documents and context
    """
    try:
        payload = {
            'query': query,
            'top_k': top_k,
            'filter': filter,
            'conversation_id': conversation_id
        }
        
        response = self.session.post(
            f"{self.base_url}/query",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        self.logger.error(f"Query failed: {str(e)}")
        raise

def delete_document(self, document_id: str) -> Dict[str, Any]:
    """
    Delete a document
    
    Args:
        document_id: ID of document to delete
        
    Returns:
        Success response
    """
    try:
        response = self.session.delete(
            f"{self.base_url}/documents/{document_id}"
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        self.logger.error(f"Delete failed: {str(e)}")
        raise

def get_config(self) -> Dict[str, Any]:
    """Get current RAG configuration"""
    try:
        response = self.session.get(f"{self.base_url}/config")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        self.logger.error(f"Get config failed: {str(e)}")
        raise
```

# ==================== LibreChat Integration ====================

class LibreChatRAGIntegration:
“””
Integration layer between LibreChat and RAG service
Handles message augmentation and context injection
“””

```
def __init__(self, rag_client: RAGClient, config: Optional[Dict] = None):
    """
    Initialize LibreChat integration
    
    Args:
        rag_client: RAG client instance
        config: Optional configuration
    """
    self.rag_client = rag_client
    self.config = config or {}
    self.top_k = self.config.get('top_k', 5)
    self.include_context = self.config.get('include_context', True)
    self.context_prefix = self.config.get('context_prefix', 
                                           "Based on the following information:\n\n")
    self.context_suffix = self.config.get('context_suffix',
                                           "\n\nPlease answer the following question: ")
    self.logger = logging.getLogger(__name__)

def augment_message(self, message: str, 
                   conversation_id: Optional[str] = None,
                   user_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Augment user message with RAG context
    
    Args:
        message: User's message
        conversation_id: Optional conversation ID
        user_id: Optional user ID
        
    Returns:
        Augmented message with context and metadata
    """
    try:
        # Query RAG system
        rag_response = self.rag_client.query(
            query=message,
            top_k=self.top_k,
            conversation_id=conversation_id
        )
        
        if not rag_response.get('documents'):
            return {
                'message': message,
                'context': None,
                'sources': [],
                'augmented': False
            }
        
        # Build augmented message
        if self.include_context:
            augmented_message = (
                f"{self.context_prefix}"
                f"{rag_response['context']}"
                f"{self.context_suffix}"
                f"{message}"
            )
        else:
            augmented_message = message
        
        # Extract sources
        sources = [
            {
                'id': doc['id'],
                'score': doc['score'],
                'metadata': doc.get('metadata', {})
            }
            for doc in rag_response['documents']
        ]
        
        return {
            'message': augmented_message,
            'original_message': message,
            'context': rag_response['context'],
            'sources': sources,
            'augmented': True,
            'metadata': rag_response.get('metadata', {})
        }
    
    except Exception as e:
        self.logger.error(f"Message augmentation failed: {str(e)}")
        # Return original message on error
        return {
            'message': message,
            'context': None,
            'sources': [],
            'augmented': False,
            'error': str(e)
        }

def format_sources(self, sources: List[Dict[str, Any]]) -> str:
    """
    Format sources for display in chat
    
    Args:
        sources: List of source documents
        
    Returns:
        Formatted sources string
    """
    if not sources:
        return ""
    
    formatted = "\n\n**Sources:**\n"
    for i, source in enumerate(sources, 1):
        metadata = source.get('metadata', {})
        score = source.get('score', 0)
        
        # Build source display
        source_text = f"{i}. "
        
        if 'title' in metadata:
            source_text += f"{metadata['title']}"
        elif 'filename' in metadata:
            source_text += f"{metadata['filename']}"
        else:
            source_text += f"Document {source['id'][:8]}"
        
        source_text += f" (relevance: {score:.2%})"
        
        formatted += source_text + "\n"
    
    return formatted
```

# ==================== Document Loaders ====================

class DocumentLoader:
“”“Base class for loading documents from various sources”””

```
def __init__(self, rag_client: RAGClient):
    self.rag_client = rag_client
    self.logger = logging.getLogger(__name__)

def load_text_file(self, filepath: str, 
                   metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Load a text file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        doc_metadata = metadata or {}
        doc_metadata['filename'] = os.path.basename(filepath)
        doc_metadata['filepath'] = filepath
        
        return self.rag_client.index_document(
            content=content,
            metadata=doc_metadata
        )
    except Exception as e:
        self.logger.error(f"Error loading file {filepath}: {str(e)}")
        raise

def load_json_file(self, filepath: str) -> Dict[str, Any]:
    """Load a JSON file with documents"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Assume JSON contains list of documents
        if isinstance(data, list):
            documents = data
        elif isinstance(data, dict) and 'documents' in data:
            documents = data['documents']
        else:
            documents = [data]
        
        return self.rag_client.index_documents(documents)
    except Exception as e:
        self.logger.error(f"Error loading JSON file {filepath}: {str(e)}")
        raise

def load_directory(self, directory: str, 
                  extensions: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Load all files from a directory
    
    Args:
        directory: Directory path
        extensions: Optional list of file extensions to include
        
    Returns:
        Indexing response
    """
    extensions = extensions or ['.txt', '.md', '.json']
    documents = []
    
    for root, _, files in os.walk(directory):
        for filename in files:
            if any(filename.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    documents.append({
                        'content': content,
                        'metadata': {
                            'filename': filename,
                            'filepath': filepath,
                            'directory': root
                        }
                    })
                except Exception as e:
                    self.logger.warning(f"Skipping {filepath}: {str(e)}")
    
    if not documents:
        raise ValueError(f"No documents found in {directory}")
    
    return self.rag_client.index_documents(documents)

def load_url(self, url: str, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Load content from a URL
    
    Args:
        url: URL to fetch
        metadata: Optional metadata
        
    Returns:
        Indexing response
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        content = response.text
        
        doc_metadata = metadata or {}
        doc_metadata['url'] = url
        doc_metadata['source_type'] = 'web'
        
        return self.rag_client.index_document(
            content=content,
            metadata=doc_metadata
        )
    except Exception as e:
        self.logger.error(f"Error loading URL {url}: {str(e)}")
        raise
```

# ==================== CLI Tool ====================

def create_cli():
“”“Create command-line interface for RAG service”””
import argparse

```
parser = argparse.ArgumentParser(description='RAG Service CLI')
parser.add_argument('--url', default='http://localhost:8000',
                   help='RAG service URL')
parser.add_argument('--api-key', help='API key')

subparsers = parser.add_subparsers(dest='command', help='Commands')

# Health check
subparsers.add_parser('health', help='Check service health')

# Index document
index_parser = subparsers.add_parser('index', help='Index documents')
index_parser.add_argument('--file', help='File to index')
index_parser.add_argument('--dir', help='Directory to index')
index_parser.add_argument('--url-source', help='URL to index')

# Query
query_parser = subparsers.add_parser('query', help='Query RAG system')
query_parser.add_argument('query', help='Query text')
query_parser.add_argument('--top-k', type=int, default=5,
                         help='Number of results')

# Config
subparsers.add_parser('config', help='Show configuration')

return parser
```

def main():
“”“Main CLI entry point”””
parser = create_cli()
args = parser.parse_args()

```
# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize client
client = RAGClient(args.url, args.api_key)

try:
    if args.command == 'health':
        result = client.health_check()
        print(json.dumps(result, indent=2))
    
    elif args.command == 'index':
        loader = DocumentLoader(client)
        
        if args.file:
            result = loader.load_text_file(args.file)
        elif args.dir:
            result = loader.load_directory(args.dir)
        elif args.url_source:
            result = loader.load_url(args.url_source)
        else:
            print("Error: Specify --file, --dir, or --url-source")
            return
        
        print(json.dumps(result, indent=2))
    
    elif args.command == 'query':
        result = client.query(args.query, top_k=args.top_k)
        
        print(f"\nQuery: {result['query']}")
        print(f"\nFound {len(result['documents'])} documents:\n")
        
        for i, doc in enumerate(result['documents'], 1):
            print(f"{i}. Score: {doc['score']:.3f}")
            print(f"   Content: {doc['content'][:200]}...")
            print()
    
    elif args.command == 'config':
        result = client.get_config()
        print(json.dumps(result, indent=2))
    
    else:
        parser.print_help()

except Exception as e:
    print(f"Error: {str(e)}")
    return 1

return 0
```

# ==================== Example Usage ====================

if **name** == “**main**”:
# Example 1: Basic client usage
print(”=” * 60)
print(“RAG Client Library Examples”)
print(”=” * 60)

```
# Initialize client
client = RAGClient(
    base_url="http://localhost:8000",
    api_key="your-api-key"
)

# Check health
print("\n1. Health Check:")
try:
    health = client.health_check()
    print(f"   Status: {health['status']}")
except Exception as e:
    print(f"   Error: {str(e)}")

# Index a document
print("\n2. Index Document:")
try:
    result = client.index_document(
        content="Python is a high-level programming language.",
        metadata={"topic": "programming", "language": "en"}
    )
    print(f"   Indexed: {result['message']}")
except Exception as e:
    print(f"   Error: {str(e)}")

# Query
print("\n3. Query:")
try:
    result = client.query(
        query="What is Python?",
        top_k=3
    )
    print(f"   Found {len(result['documents'])} documents")
    if result['documents']:
        print(f"   Top result score: {result['documents'][0]['score']:.3f}")
except Exception as e:
    print(f"   Error: {str(e)}")

# Example 2: LibreChat integration
print("\n" + "=" * 60)
print("LibreChat Integration Example")
print("=" * 60)

integration = LibreChatRAGIntegration(client)

try:
    augmented = integration.augment_message(
        message="How do I use Python for data analysis?",
        conversation_id="conv_123"
    )
    
    print(f"\nAugmented: {augmented['augmented']}")
    if augmented['sources']:
        print(f"Sources: {len(augmented['sources'])}")
        print(integration.format_sources(augmented['sources']))
except Exception as e:
    print(f"Error: {str(e)}")
```