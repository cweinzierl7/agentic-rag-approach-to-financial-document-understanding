""" 
Recursive character text chunker module.
"""
import os
import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import asyncio
from dataclasses import dataclass, field
import logging

from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from ..ingestion.data_prep import Item
except ImportError:
    # For direct execution or testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from ingestion.data_prep import Item

from dotenv import load_dotenv


@dataclass
class ChunkingConfig:
    """Configuration for chunking."""
    chunk_size: int = 200
    chunk_overlap: int = 0
    max_chunk_size: int = 400
    min_chunk_size: int = 50
    chunk_separator: List[str] = field(default_factory=lambda: ["\n\n", "\n", ". ", "?", "!", " ", ""])
    chunking_method: str = "recursive"
    # preserve_structure: bool = True

    def __post_init__(self):
        """Validate the chunking configuration."""
        if self.chunk_size < self.min_chunk_size:
            raise ValueError(f"chunk_size must be at least {self.min_chunk_size}")
        if self.chunk_size > self.max_chunk_size:
            raise ValueError(f"chunk_size must not exceed {self.max_chunk_size}")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.min_chunk_size <= 0:
            raise ValueError("min_chunk_size must be greater than 0")

@dataclass
class DocumentChunk:
    """Represents a chunk with metadata."""
    content: str
    index: int
    md: str
    metadata: Dict[str, Any]
    token_count: Optional[int] = None

    def __post_init__(self):
        if self.token_count is None: 
            # rough estimate of token count
            self.token_count = len(self.content) // 4

class RecursiveCharacterTextChunker:
    """Recursive character text splitter that splits text into chunks based on specified separators."""

    def __init__(self, config: ChunkingConfig):
        """Initialize the text splitter with chunk size, overlap, and separators."""
        self.config = config
        
    async def chunk_documents(
        self,
        content: list,
    ) -> List[DocumentChunk]:
        """ 
        Chunk the documents content on item base into smaller pieces.
        """
        if not content:
            return []

        try: 
            recursive_chunks = await self._recursive_chunk(content)
            if recursive_chunks:
                return self._create_chunk_objects(recursive_chunks)
        except Exception as e:
            logger.error(f"Error during recursive chunking: {e}")
            return []


    async def _recursive_chunk(self, content: list[Item]) -> List[Dict[str, Any]]:
        """ 
        Recursively chunk the content based on separators. 
        Returns:
            List of dicts with 'chunk', 'metadata', and 'md'.
        """
        child_splitters = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size, 
            separators=self.config.chunk_separator, 
            chunk_overlap=self.config.chunk_overlap
        )

        chunks = []
        
        for item in content:
            metadata = {
                "title": item.doc_title,
                "source": item.file_path,
                "page": item.page,
                "type": item.type_item,
                "heading_lvl1": item.heading_lvl1,
                "heading_lvl2": item.heading_lvl2,
                "heading_lvl3": item.heading_lvl3,
                "table_idx": item.table_idx,
                "item_idx": item.item_idx,
                "client": item.client,
            }

            if item.type_item == "table":
                chunks.append({
                    "chunk": item.md,
                    "metadata": metadata,
                    "md": item.table_md
                })
            else:
                sub_chunks = child_splitters.split_text(item.md)
                for sub_chunk in sub_chunks:
                    chunks.append({
                        "chunk": sub_chunk,
                        "metadata": metadata,
                        "md": item.md
                    })

        return chunks

    def _create_chunk_objects(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        """Create DocumentChunk objects from chunk data."""
        document_chunks = []
        for idx, chunk_data in enumerate(chunks):
            document_chunks.append(DocumentChunk(
                content=chunk_data["chunk"],
                index=idx,
                md=chunk_data.get("md", ""),
                metadata=chunk_data["metadata"]
            ))
        return document_chunks



# Factory function
def create_chunker(config: ChunkingConfig):
    """
    Create appropriate chunker based on configuration.
    
    Args:
        config: Chunking configuration
    
    Returns:
        Chunker instance
    """
    if config.chunking_method == "recursive":
        return RecursiveCharacterTextChunker(config)
    else:
        raise ValueError(f"Unsupported chunking method: {config.chunking_method}")


async def main():
    # Example usage
    config = ChunkingConfig(
        chunk_size=400,
    )

    chunker = create_chunker(config)

    # Example content list
    content = [
        # Populate with document items having attributes like doc_title, file_path, page, type_item, md, etc.
    ]

    chunks = await chunker.chunk_documents(content)
    for chunk in chunks:
        print(f"Chunk {chunk.index}: {chunk.content[:50]}...")
    
if __name__ == "__main__":
    asyncio.run(main())