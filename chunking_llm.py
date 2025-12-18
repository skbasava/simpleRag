“””
Production-grade LLM-based XML Chunking System
Supports multiple chunking strategies with validation and error handling
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

@dataclass
class Chunk:
“”“Represents a single chunk of XML content”””
id: str
content: str
metadata: ChunkMetadata

```
def to_dict(self) -> Dict:
    """Convert chunk to dictionary"""
    return {
        'id': self.id,
        'content': self.content,
        'metadata': asdict(self.metadata)
    }
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
```

class AnthropicClient(LLMClient):
“”“Anthropic Claude client for LLM operations”””

```
def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
    """Initialize Anthropic client"""
    self.client = anthropic.Anthropic(api_key=api_key)
    self.model = model

def generate(self, prompt: str, max_tokens: int = 4096) -> str:
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
    """
    Initialize XML chunker
    
    Args:
        llm_client: LLM client for generating chunks
        strategy: Chunking strategy to use
        min_chunk_size: Minimum chunk size in tokens
        max_chunk_size: Maximum chunk size in tokens
        atomic_tags: Tags that should never be split
        preferred_split_tags: Preferred tags for splitting
    """
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

def chunk_xml(
    self,
    xml_content: str,
    source_file: Optional[str] = None
) -> List[Chunk]:
    """
    Chunk XML content using specified strategy
    
    Args:
        xml_content: XML content as string
        source_file: Optional source file path for metadata
        
    Returns:
        List of Chunk objects
    """
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
        # Extract JSON from response (handle potential markdown code blocks)
        json_match = re.search(r'\[[\s\S]*\]', response)
        if json_match:
            json_str = json_match.group(0)
        else:
            json_str = response
        
        chunks_data = json.loads(json_str)
        
        chunks = []
        for idx, chunk_data in enumerate(chunks_data):
            # Generate unique chunk ID
            chunk_id = chunk_data.get('chunk_id') or self._generate_chunk_id(
                chunk_data['content'], idx
            )
            
            # Count tokens
            token_count = self.token_counter.count(chunk_data['content'])
            
            # Create metadata
            metadata = ChunkMetadata(
                chunk_id=chunk_id,
                parent_path=chunk_data['metadata'].get('parent_path', 'root'),
                attributes=chunk_data['metadata'].get('attributes', {}),
                chunk_type=chunk_data['metadata'].get('chunk_type', 'unknown'),
                token_count=token_count,
                sequence_number=idx,
                source_file=source_file
            )
            
            # Create chunk
            chunk = Chunk(
                id=chunk_id,
                content=chunk_data['content'],
                metadata=metadata
            )
            chunks.append(chunk)
        
        return chunks
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        logger.debug(f"Response was: {response[:500]}...")
        raise ValueError("LLM response is not valid JSON")

def _validate_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
    """Validate all chunks and filter out invalid ones"""
    valid_chunks = []
    
    for chunk in chunks:
        if self.validator.validate_chunk(chunk.content):
            # Check size constraints
            if self.min_chunk_size <= chunk.metadata.token_count <= self.max_chunk_size * 1.5:
                valid_chunks.append(chunk)
            else:
                logger.warning(
                    f"Chunk {chunk.id} size {chunk.metadata.token_count} "
                    f"outside acceptable range [{self.min_chunk_size}, {self.max_chunk_size * 1.5}]"
                )
        else:
            logger.warning(f"Chunk {chunk.id} failed validation")
    
    return valid_chunks

def _finalize_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
    """Finalize chunks with correct sequence numbers and totals"""
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

class ChunkExporter:
“”“Export chunks to various formats”””

```
@staticmethod
def to_json(chunks: List[Chunk], output_path: Path) -> None:
    """Export chunks to JSON file"""
    data = [chunk.to_dict() for chunk in chunks]
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Exported {len(chunks)} chunks to {output_path}")

@staticmethod
def to_jsonl(chunks: List[Chunk], output_path: Path) -> None:
    """Export chunks to JSONL file (one chunk per line)"""
    with open(output_path, 'w', encoding='utf-8') as f:
        for chunk in chunks:
            f.write(json.dumps(chunk.to_dict(), ensure_ascii=False) + '\n')
    logger.info(f"Exported {len(chunks)} chunks to {output_path}")

@staticmethod
def print_summary(chunks: List[Chunk]) -> None:
    """Print summary statistics of chunks"""
    total_tokens = sum(c.metadata.token_count for c in chunks)
    avg_tokens = total_tokens / len(chunks) if chunks else 0
    
    print("\n" + "="*60)
    print("CHUNKING SUMMARY")
    print("="*60)
    print(f"Total chunks: {len(chunks)}")
    print(f"Total tokens: {total_tokens}")
    print(f"Average tokens per chunk: {avg_tokens:.1f}")
    print(f"Min tokens: {min(c.metadata.token_count for c in chunks)}")
    print(f"Max tokens: {max(c.metadata.token_count for c in chunks)}")
    print("="*60 + "\n")
```

# Example usage

def main():
“”“Example usage of the XML chunking system”””

```
# Sample XML content
sample_xml = """<?xml version="1.0" encoding="UTF-8"?>
```

<document>
    <metadata>
        <title>Sample Technical Documentation</title>
        <author>John Doe</author>
        <date>2024-12-18</date>
    </metadata>
    <chapter id="ch1" title="Introduction">
        <section id="sec1.1">
            <title>Overview</title>
            <paragraph>This is the introduction to our technical documentation. 
            It provides a comprehensive overview of the system architecture and design principles.
            The system is built using modern cloud-native technologies and follows best practices
            for scalability, reliability, and maintainability.</paragraph>
            <paragraph>Key features include real-time processing, distributed caching,
            and microservices architecture. Each component is designed to be independently
            deployable and scalable.</paragraph>
        </section>
        <section id="sec1.2">
            <title>Architecture</title>
            <subsection id="subsec1.2.1">
                <title>System Components</title>
                <paragraph>The system consists of multiple layers including presentation,
                business logic, and data access layers. Each layer has specific responsibilities
                and communicates through well-defined interfaces.</paragraph>
                <list>
                    <item>Frontend: React-based SPA</item>
                    <item>Backend: Python microservices</item>
                    <item>Database: PostgreSQL with pgvector</item>
                    <item>Cache: Redis cluster</item>
                </list>
            </subsection>
        </section>
    </chapter>
    <chapter id="ch2" title="Implementation">
        <section id="sec2.1">
            <title>Setup Guide</title>
            <paragraph>This section describes how to set up the development environment
            and deploy the application. Follow these steps carefully to ensure proper
            configuration.</paragraph>
            <code language="bash">
# Install dependencies
pip install -r requirements.txt

# Run migrations

python manage.py migrate

# Start server

python manage.py runserver
</code>
</section>
</chapter>
</document>”””

```
# Initialize chunker (you need to provide your Anthropic API key)
api_key = "your-api-key-here"  # Replace with actual API key
llm_client = AnthropicClient(api_key=api_key)

chunker = XMLChunker(
    llm_client=llm_client,
    strategy=ChunkingStrategy.SEMANTIC,
    min_chunk_size=300,
    max_chunk_size=800,
    atomic_tags=['table', 'code', 'figure', 'list'],
    preferred_split_tags=['chapter', 'section', 'subsection']
)

try:
    # Chunk the XML
    chunks = chunker.chunk_xml(
        xml_content=sample_xml,
        source_file="sample_doc.xml"
    )
    
    # Print summary
    ChunkExporter.print_summary(chunks)
    
    # Export to JSON
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    ChunkExporter.to_json(chunks, output_dir / "chunks.json")
    ChunkExporter.to_jsonl(chunks, output_dir / "chunks.jsonl")
    
    # Print first chunk as example
    if chunks:
        print("Example chunk:")
        print(json.dumps(chunks[0].to_dict(), indent=2))
    
except Exception as e:
    logger.error(f"Chunking failed: {e}")
    raise
```

if **name** == “**main**”:
main()