“””
Production-grade LLM-based XML Chunking System with pgvector Integration
Chunks XML files and stores them in PostgreSQL with pgvector embeddings
“””

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import json
import logging
from pathlib import Path
import hashlib
import re
from abc import ABC, abstractmethod
import anthropic
import tiktoken
import psycopg2
from psycopg2.extras import execute_values
import numpy as np
from datetime import datetime

# Configure logging

logging.basicConfig(
level=logging.INFO,
format=’%(asctime)s - %(name)s - %(levelname)s - %(message)s’
)
logger = logging.getLogger(**name**)

class ChunkingStrategy(Enum):
“”“Supported chunking strategies”””
SEMANTIC = “semantic”
HIERARCHICAL = “hierarchical”
ADAPTIVE = “adaptive”
TAG_PRIORITY = “tag_priority”

@dataclass
class ChunkMetadata:
“”“Metadata for each chunk”””
chunk_id: str
parent_path: str
attributes: Dict[str, Any]
chunk_type: str
token_count: int
sequence_number: int
total_chunks: Optional[int] = None
source_file: Optional[str] = None
created_at: Optional[str] = None

@dataclass
class Chunk:
“”“Represents a single chunk of XML content”””
id: str
content: str
metadata: ChunkMetadata
embedding: Optional[np.ndarray] = None

```
def to_dict(self) -> Dict:
    """Convert chunk to dictionary"""
    result = {
        'id': self.id,
        'content': self.content,
        'metadata': asdict(self.metadata)
    }
    if self.embedding is not None:
        result['embedding'] = self.embedding.tolist()
    return result
```

class TokenCounter:
“”“Utility class for counting tokens”””

```
def __init__(self, model: str = "cl100k_base"):
    """Initialize token counter with encoding model"""
    try:
        self.encoding = tiktoken.get_encoding(model)
    except Exception as e:
        logger.warning(f"Failed to load tiktoken encoding: {e}. Using character approximation.")
        self.encoding = None

def count(self, text: str) -> int:
    """Count tokens in text"""
    if self.encoding:
        return len(self.encoding.encode(text))
    else:
        # Approximate: 1 token ≈ 4 characters
        return len(text) // 4
```

class XMLValidator:
“”“Validates XML content”””

```
@staticmethod
def is_well_formed(xml_string: str) -> Tuple[bool, Optional[str]]:
    """Check if XML string is well-formed"""
    try:
        ET.fromstring(xml_string)
        return True, None
    except ET.ParseError as e:
        return False, str(e)

@staticmethod
def validate_chunk(chunk_content: str) -> bool:
    """Validate a chunk of XML content"""
    is_valid, error = XMLValidator.is_well_formed(chunk_content)
    if not is_valid:
        logger.warning(f"Invalid XML chunk: {error}")
    return is_valid
```

class PromptBuilder:
“”“Builds prompts for different chunking strategies”””

```
@staticmethod
def build_semantic_prompt(
    xml_content: str,
    target_size: int,
    atomic_tags: List[str]
) -> str:
    """Build prompt for semantic chunking"""
    return f"""You are an XML document analyzer. Your task is to identify optimal chunk boundaries in XML documents while preserving semantic coherence.
```

Given this XML content:
<xml_content>
{xml_content}
</xml_content>

Instructions:

1. Identify natural semantic boundaries where content can be split
1. Each chunk should be self-contained and meaningful
1. Preserve complete XML tags (no broken tags)
1. Keep related content together (e.g., a section with all its subsections)
1. Target chunk size: approximately {target_size} tokens
1. Never split these atomic tags: {’, ’.join(atomic_tags)}

Return your analysis as a JSON array with this exact structure:
[
{{
“chunk_id”: “chunk_001”,
“content”: “<complete_xml>…</complete_xml>”,
“metadata”: {{
“parent_path”: “root/section1”,
“attributes”: {{}},
“chunk_type”: “section”,
“reasoning”: “why this is a good chunk boundary”
}}
}}
]

IMPORTANT:

- Return ONLY the JSON array, no additional text
- Ensure all chunks are valid, well-formed XML
- Maintain document order
  “””
  
  @staticmethod
  def build_hierarchical_prompt(
  xml_content: str,
  min_size: int,
  max_size: int,
  preferred_tags: List[str]
  ) -> str:
  “”“Build prompt for hierarchical chunking”””
  return f””“Analyze this XML document and create chunks based on hierarchical structure:

<xml_document>
{xml_content}
</xml_document>

Chunking Requirements:

1. Identify the document’s hierarchical structure
1. Prefer splitting at these tags (in order): {’, ’.join(preferred_tags)}
1. Chunk size range: {min_size} to {max_size} tokens
1. Include parent context in metadata
1. Ensure each chunk is semantically complete

Return a JSON array with this structure:
[
{{
“chunk_id”: “chunk_001”,
“content”: “<xml>…</xml>”,
“metadata”: {{
“parent_path”: “root/chapter/section”,
“attributes”: {{}},
“chunk_type”: “section”,
“hierarchy_level”: 2
}}
}}
]

Return ONLY the JSON array, no other text.
“””

```
@staticmethod
def build_adaptive_prompt(
    xml_content: str,
    min_size: int,
    max_size: int,
    atomic_tags: List[str]
) -> str:
    """Build prompt for adaptive chunking"""
    return f"""Intelligently chunk this XML based on content density and structure:
```

<xml>
{xml_content}
</xml>

Adaptive Strategy:

1. Analyze content density (text vs markup ratio)
1. For text-heavy sections: chunk by size ({min_size}-{max_size} tokens)
1. For structure-heavy sections: chunk by logical XML elements
1. Always preserve complete: {’, ’.join(atomic_tags)}
1. Maintain semantic boundaries

Return a JSON array:
[
{{
“chunk_id”: “chunk_001”,
“content”: “<xml>…</xml>”,
“metadata”: {{
“parent_path”: “path”,
“attributes”: {{}},
“chunk_type”: “mixed”,
“strategy_used”: “semantic|size-based|hybrid”
}}
}}
]

Return ONLY the JSON array.
“””

class LLMClient(ABC):
“”“Abstract base class for LLM clients”””

```
@abstractmethod
def generate(self, prompt: str) -> str:
    """Generate response from LLM"""
    pass

@abstractmethod
def generate_embedding(self, text: str) -> np.ndarray:
    """Generate embedding vector for text"""
    pass
```

class AnthropicClient(LLMClient):
“”“Anthropic Claude client for LLM operations”””

```
def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
    """Initialize Anthropic client"""
    self.client = anthropic.Anthropic(api_key=api_key)
    self.model = model
    self.embedding_dim = 1024  # Claude embeddings dimension

def generate(self, prompt: str, max_tokens: int = 8000) -> str:
    """Generate response using Claude"""
    try:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise

def generate_embedding(self, text: str) -> np.ndarray:
    """
    Generate embedding vector for text
    Note: Replace this with actual embedding API when available
    For now, using a placeholder that creates deterministic embeddings
    """
    try:
        # TODO: Replace with actual Anthropic embedding API when available
        # For now, using a deterministic hash-based embedding
        hash_value = hashlib.sha256(text.encode()).digest()
        # Convert to float array and normalize
        embedding = np.frombuffer(hash_value, dtype=np.uint8).astype(np.float32)
        # Pad or truncate to desired dimension
        if len(embedding) < self.embedding_dim:
            embedding = np.pad(embedding, (0, self.embedding_dim - len(embedding)))
        else:
            embedding = embedding[:self.embedding_dim]
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding
    except Exception as e:
        logger.error(f"Embedding generation failed: {e}")
        raise
```

class PgVectorStore:
“”“PostgreSQL with pgvector integration”””

```
def __init__(
    self,
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    table_name: str = "xml_chunks"
):
    """Initialize connection to PostgreSQL"""
    self.connection_params = {
        'host': host,
        'port': port,
        'database': database,
        'user': user,
        'password': password
    }
    self.table_name = table_name
    self.conn = None

def connect(self) -> None:
    """Establish database connection"""
    try:
        self.conn = psycopg2.connect(**self.connection_params)
        logger.info("Connected to PostgreSQL database")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

def close(self) -> None:
    """Close database connection"""
    if self.conn:
        self.conn.close()
        logger.info("Database connection closed")

def create_table(self, embedding_dim: int = 1024) -> None:
    """Create table with pgvector extension"""
    try:
        with self.conn.cursor() as cur:
            # Enable pgvector extension
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Create table
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                embedding vector({embedding_dim}),
                chunk_id TEXT NOT NULL,
                parent_path TEXT,
                attributes JSONB,
                chunk_type TEXT,
                token_count INTEGER,
                sequence_number INTEGER,
                total_chunks INTEGER,
                source_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                metadata JSONB
            );
            """
            cur.execute(create_table_sql)
            
            # Create indexes
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_embedding_idx 
                ON {self.table_name} 
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """)
            
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_source_file_idx 
                ON {self.table_name}(source_file);
            """)
            
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_chunk_type_idx 
                ON {self.table_name}(chunk_type);
            """)
            
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.table_name}_metadata_idx 
                ON {self.table_name} 
                USING gin(metadata);
            """)
            
            self.conn.commit()
            logger.info(f"Table {self.table_name} created successfully with indexes")
    except Exception as e:
        self.conn.rollback()
        logger.error(f"Failed to create table: {e}")
        raise

def insert_chunks(self, chunks: List[Chunk]) -> int:
    """Insert chunks into database"""
    try:
        with self.conn.cursor() as cur:
            # Prepare data for insertion
            data = []
            for chunk in chunks:
                data.append((
                    chunk.id,
                    chunk.content,
                    chunk.embedding.tolist() if chunk.embedding is not None else None,
                    chunk.metadata.chunk_id,
                    chunk.metadata.parent_path,
                    json.dumps(chunk.metadata.attributes),
                    chunk.metadata.chunk_type,
                    chunk.metadata.token_count,
                    chunk.metadata.sequence_number,
                    chunk.metadata.total_chunks,
                    chunk.metadata.source_file,
                    chunk.metadata.created_at,
                    json.dumps(asdict(chunk.metadata))
                ))
            
            # Bulk insert
            insert_sql = f"""
                INSERT INTO {self.table_name} 
                (id, content, embedding, chunk_id, parent_path, attributes, 
                 chunk_type, token_count, sequence_number, total_chunks, 
                 source_file, created_at, metadata)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    content = EXCLUDED.content,
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata;
            """
            
            execute_values(cur, insert_sql, data)
            self.conn.commit()
            
            logger.info(f"Inserted {len(chunks)} chunks into {self.table_name}")
            return len(chunks)
    except Exception as e:
        self.conn.rollback()
        logger.error(f"Failed to insert chunks: {e}")
        raise

def search_similar(
    self,
    query_embedding: np.ndarray,
    limit: int = 10,
    source_file: Optional[str] = None
) -> List[Dict]:
    """Search for similar chunks using vector similarity"""
    try:
        with self.conn.cursor() as cur:
            where_clause = ""
            params = [query_embedding.tolist(), limit]
            
            if source_file:
                where_clause = "WHERE source_file = %s"
                params = [query_embedding.tolist(), source_file, limit]
            
            search_sql = f"""
                SELECT id, content, chunk_id, parent_path, chunk_type,
                       token_count, source_file, metadata,
                       1 - (embedding <=> %s::vector) as similarity
                FROM {self.table_name}
                {where_clause}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """
            
            if source_file:
                cur.execute(search_sql, params)
            else:
                cur.execute(search_sql, [query_embedding.tolist(), query_embedding.tolist(), limit])
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'content': row[1],
                    'chunk_id': row[2],
                    'parent_path': row[3],
                    'chunk_type': row[4],
                    'token_count': row[5],
                    'source_file': row[6],
                    'metadata': row[7],
                    'similarity': float(row[8])
                })
            
            return results
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise

def delete_by_source_file(self, source_file: str) -> int:
    """Delete all chunks from a specific source file"""
    try:
        with self.conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {self.table_name} WHERE source_file = %s;",
                (source_file,)
            )
            deleted = cur.rowcount
            self.conn.commit()
            logger.info(f"Deleted {deleted} chunks from {source_file}")
            return deleted
    except Exception as e:
        self.conn.rollback()
        logger.error(f"Failed to delete chunks: {e}")
        raise
```

class XMLChunker:
“”“Main XML chunking orchestrator”””

```
def __init__(
    self,
    llm_client: LLMClient,
    strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC,
    min_chunk_size: int = 500,
    max_chunk_size: int = 1500,
    atomic_tags: Optional[List[str]] = None,
    preferred_split_tags: Optional[List[str]] = None
):
    """Initialize XML chunker"""
    self.llm_client = llm_client
    self.strategy = strategy
    self.min_chunk_size = min_chunk_size
    self.max_chunk_size = max_chunk_size
    self.atomic_tags = atomic_tags or ['table', 'code', 'figure', 'list']
    self.preferred_split_tags = preferred_split_tags or [
        'chapter', 'section', 'subsection', 'paragraph', 'div'
    ]
    self.token_counter = TokenCounter()
    self.validator = XMLValidator()

def chunk_xml_file(
    self,
    xml_file_path: Path,
    generate_embeddings: bool = True
) -> List[Chunk]:
    """
    Chunk XML file and optionally generate embeddings
    
    Args:
        xml_file_path: Path to XML file
        generate_embeddings: Whether to generate embeddings
        
    Returns:
        List of Chunk objects with embeddings
    """
    logger.info(f"Processing XML file: {xml_file_path}")
    
    # Read XML file
    try:
        with open(xml_file_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()
    except Exception as e:
        logger.error(f"Failed to read XML file: {e}")
        raise
    
    # Chunk XML content
    chunks = self.chunk_xml(xml_content, source_file=str(xml_file_path))
    
    # Generate embeddings if requested
    if generate_embeddings:
        logger.info("Generating embeddings for chunks...")
        chunks = self._generate_embeddings(chunks)
    
    return chunks

def chunk_xml(
    self,
    xml_content: str,
    source_file: Optional[str] = None
) -> List[Chunk]:
    """Chunk XML content using specified strategy"""
    logger.info(f"Starting XML chunking with {self.strategy.value} strategy")
    
    # Validate input XML
    is_valid, error = self.validator.is_well_formed(xml_content)
    if not is_valid:
        raise ValueError(f"Invalid input XML: {error}")
    
    # Build prompt based on strategy
    prompt = self._build_prompt(xml_content)
    
    # Generate chunks using LLM
    logger.info("Requesting LLM to generate chunks...")
    response = self.llm_client.generate(prompt)
    
    # Parse and validate response
    chunks = self._parse_llm_response(response, source_file)
    
    # Validate all chunks
    chunks = self._validate_chunks(chunks)
    
    # Update sequence numbers and total
    chunks = self._finalize_chunks(chunks)
    
    logger.info(f"Successfully created {len(chunks)} chunks")
    return chunks

def _generate_embeddings(self, chunks: List[Chunk]) -> List[Chunk]:
    """Generate embeddings for all chunks"""
    for idx, chunk in enumerate(chunks):
        try:
            # Create embedding text from content and metadata
            embedding_text = self._prepare_embedding_text(chunk)
            chunk.embedding = self.llm_client.generate_embedding(embedding_text)
            
            if (idx + 1) % 10 == 0:
                logger.info(f"Generated embeddings for {idx + 1}/{len(chunks)} chunks")
        except Exception as e:
            logger.error(f"Failed to generate embedding for chunk {chunk.id}: {e}")
            # Set to zero vector as fallback
            chunk.embedding = np.zeros(1024, dtype=np.float32)
    
    return chunks

def _prepare_embedding_text(self, chunk: Chunk) -> str:
    """Prepare text for embedding generation"""
    # Combine content with key metadata for better semantic search
    parts = [chunk.content]
    
    if chunk.metadata.parent_path:
        parts.append(f"Path: {chunk.metadata.parent_path}")
    
    if chunk.metadata.chunk_type:
        parts.append(f"Type: {chunk.metadata.chunk_type}")
    
    return "\n".join(parts)

def _build_prompt(self, xml_content: str) -> str:
    """Build prompt based on chunking strategy"""
    target_size = (self.min_chunk_size + self.max_chunk_size) // 2
    
    if self.strategy == ChunkingStrategy.SEMANTIC:
        return PromptBuilder.build_semantic_prompt(
            xml_content, target_size, self.atomic_tags
        )
    elif self.strategy == ChunkingStrategy.HIERARCHICAL:
        return PromptBuilder.build_hierarchical_prompt(
            xml_content, self.min_chunk_size, 
            self.max_chunk_size, self.preferred_split_tags
        )
    elif self.strategy == ChunkingStrategy.ADAPTIVE:
        return PromptBuilder.build_adaptive_prompt(
            xml_content, self.min_chunk_size,
            self.max_chunk_size, self.atomic_tags
        )
    else:
        raise ValueError(f"Unsupported strategy: {self.strategy}")

def _parse_llm_response(
    self,
    response: str,
    source_file: Optional[str]
) -> List[Chunk]:
    """Parse LLM response into Chunk objects"""
    try:
        # Extract JSON from response
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = response
        
        chunks_data = json.loads(json_str)
        
        chunks = []
        created_at = datetime.utcnow().isoformat()
        
        for idx, chunk_data in enumerate(chunks_data):
            chunk_id = chunk_data.get('chunk_id') or self._generate_chunk_id(
                chunk_data['content'], idx
            )
            
            token_count = self.token_counter.count(chunk_data['content'])
            
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                parent_path=chunk_data['metadata'].get('parent_path', 'root'),
                attributes=chunk_data['metadata'].get('attributes', {}),
                chunk_type=chunk_data['metadata'].get('chunk_type', 'unknown'),
                token_count=token_count,
                sequence_number=idx,
                source_file=source_file,
                created_at=created_at
            )
            
            chunk = Chunk(
                id=chunk_id,
                content=chunk_data['content'],
                metadata=metadata
            )
            chunks.append(chunk)
        
        return chunks
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        raise ValueError("LLM response is not valid JSON")

def _validate_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
    """Validate all chunks"""
    valid_chunks = []
    
    for chunk in chunks:
        if self.validator.validate_chunk(chunk.content):
            if self.min_chunk_size <= chunk.metadata.token_count <= self.max_chunk_size * 1.5:
                valid_chunks.append(chunk)
            else:
                logger.warning(
                    f"Chunk {chunk.id} size {chunk.metadata.token_count} "
                    f"outside acceptable range"
                )
        else:
            logger.warning(f"Chunk {chunk.id} failed validation")
    
    return valid_chunks

def _finalize_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
    """Finalize chunks with correct sequence numbers"""
    total = len(chunks)
    for idx, chunk in enumerate(chunks):
        chunk.metadata.sequence_number = idx
        chunk.metadata.total_chunks = total
    return chunks

@staticmethod
def _generate_chunk_id(content: str, index: int) -> str:
    """Generate unique chunk ID"""
    hash_obj = hashlib.md5(content.encode())
    return f"chunk_{index:04d}_{hash_obj.hexdigest()[:8]}"
```

class XMLChunkingPipeline:
“”“End-to-end pipeline for chunking XML and storing in pgvector”””

```
def __init__(
    self,
    llm_client: LLMClient,
    vector_store: PgVectorStore,
    chunker_config: Optional[Dict] = None
):
    """Initialize pipeline"""
    self.llm_client = llm_client
    self.vector_store = vector_store
    
    chunker_config = chunker_config or {}
    self.chunker = XMLChunker(llm_client=llm_client, **chunker_config)

def process_file(
    self,
    xml_file_path: Path,
    replace_existing: bool = False
) -> int:
    """
    Process XML file and store in vector database
    
    Args:
        xml_file_path: Path to XML file
        replace_existing: Whether to replace existing chunks from this file
        
    Returns:
        Number of chunks stored
    """
    logger.info(f"Processing file: {xml_file_path}")
    
    # Delete existing chunks if requested
    if replace_existing:
        self.vector_store.delete_by_source_file(str(xml_file_path))
    
    # Chunk XML file
    chunks = self.chunker.chunk_xml_file(
        xml_file_path=xml_file_path,
        generate_embeddings=True
    )
    
    # Store in database
    count = self.vector_store.insert_chunks(chunks)
    
    logger.info(f"Successfully processed {xml_file_path}: {count} chunks stored")
    return count

def process_directory(
    self,
    directory_path: Path,
    pattern: str = "*.xml",
    replace_existing: bool = False
) -> Dict[str, int]:
    """
    Process all XML files in directory
    
    Args:
        directory_path: Path to directory
        pattern: File pattern to match
        replace_existing: Whether to replace existing chunks
        
    Returns:
        Dictionary mapping file paths to chunk counts
    """
    results = {}
    xml_files = list(directory_path.glob(pattern))
    
    logger.info(f"Found {len(xml_files)} XML files in {directory_path}")
    
    for xml_file in xml_files:
        try:
            count = self.process_file(xml_file, replace_existing)
            results[str(xml_file)] = count
        except Exception as e:
            logger.error(f"Failed to process {xml_file}: {e}")
            results[str(xml_file)] = -1
    
    return results

def search(
    self,
    query_text: str,
    limit: int = 10,
    source_file: Optional[str] = None
) -> List[Dict]:
    """
    Search for similar chunks
    
    Args:
        query_text: Search query
        limit: Maximum number of results
        source_file: Optional filter by source file
        
    Returns:
        List of matching chunks with similarity scores
    """
    # Generate query embedding
    query_embedding = self.llm_client.generate_embedding(query_text)
    
    # Search vector store
    results = self.vector_store.search_similar(
        query_embedding=query_embedding,
        limit=limit,
        source_file=source_file
    )
    
    return results
```

def main():
“”“Example usage”””

```
# Configuration
ANTHROPIC_API_KEY = "your-api-key-here"
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'vector_db',
    'user': 'postgres',
    'password': 'your-password'
}

# Initialize components
llm_client = AnthropicClient(api_key=ANTHROPIC_API_KEY)
vector_store = PgVectorStore(**DB_CONFIG, table_name="xml_chunks")

# Connect to database
vector_store.connect()

try:
    # Create table with indexes
    vector_store.create_table(embedding_dim=1024)
    
    # Initialize pipeline
    pipeline = XMLChunkingPipeline(
        llm_client=llm_client,
        vector_store=vector_store,
        chunker_config={
            'strategy': ChunkingStrategy.SEMANTIC,
            'min_chunk_size': 300,
            'max_chunk_size': 800,
            'atomic_tags': ['table', 'code', 'figure', 'list'],
            'preferred_split_tags': ['chapter', 'section', 'subsection']
        }
    )
    
    # Process single file
    xml_file = Path("sample_document.xml")
    if xml_file.exists():
        count = pipeline.process_file(xml_file, replace_existing=True)
        print(f"Processed {xml_file}: {count} chunks stored")
    
    # Process directory
    xml_dir = Path("xml_documents")
    if xml_dir.exists():
        results = pipeline.process_directory(xml_dir, replace_existing=True)
        print(f"\nProcessed {len(results)} files:")
        for file, count in results.items():
            print(f"  {file}: {count} chunks")
    
    # Example search
    search_results = pipeline.search(
        query_text="system architecture components",
        limit=5
    )
    
    print("\n" + "="*60)
    print("SEARCH RESULTS")
    print("="*60)
    for idx, result in enumerate(search_results, 1):
        print(f"\n{idx}. Similarity: {result['similarity']:.4f}")
        print(f"   Source: {result['source_file']}")
        print(f"   Type: {result['chunk_type']}")
        print(f"   Path: {result['parent_path']}")
        print(f"   Content preview: {result['content'][:200]}...")
    
finally:
    vector_store.close()
```

if **name** == “**main**”:
main()