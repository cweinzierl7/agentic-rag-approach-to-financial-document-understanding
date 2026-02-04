"""
Document embedding generation for vector search.
"""


import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json

from openai import RateLimitError, APIError
from dotenv import load_dotenv

from .chunker import DocumentChunk


# Import flexible providers
try:
    from ..agent.providers import get_embedding_client, get_embedding_model
except ImportError:
    # For direct execution or testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.providers import get_embedding_client, get_embedding_model

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

embedding_client = get_embedding_client()
EMBEDDING_MODEL = get_embedding_model()

class EmbeddingGenerator:
    """ Generate embeddings for document chunks """
    def __init__(
        self, 
        model: str = EMBEDDING_MODEL,
        batch_size: int = 100, 
        max_retries: int = 3,
        retry_delay = 1.0 
    ):
        """ Initialize the embedding generator

        Args:
            model: embedding model name
            batch_size: number of chunks to embed in one request
            max_retries: number of times to retry on failure
            retry_delay: wait time in seconds between retries

        Others:
            model_config: dictionary with model configurations (dimensions, max_tokens)
                dimensions: number of dimensions in the embedding vector 
                max_tokens: maximum number of tokens allowed in the input text
        """
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.model_config = {
            "text-embedding-3-small": {
                "dimensions": 1536,
                "max_tokens": 8191
            },
            "text-embedding-3-large": {
                "dimensions": 3072,
                "max_tokens": 8191
            }
        }
        if model not in self.model_config:
            raise ValueError(f"Unsupported model: {model}") # has to be exchanged with logger info
            self.config = {dimensions: 1536, max_tokens: 8191}
        else: 
            self.config = self.model_config[model]

    async def generate_embeddings(self, text: str) -> List[float]:
        """ 
        Generate embedding for a single text chunk 

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """

        # Truncate text if too long 
        if len(text) > self.config["max_tokens"] * 4: # rough estimate of tokens
            text = text[:self.config["max_tokens"] * 4]

        for attempt in range(self.max_retries):
            try:
                response = await embedding_client.embeddings.create(
                    model=self.model,
                    input=text
                )
                return response.data[0].embedding
            
            except RateLimitError as e:
                if attempt == slef.max_retries - 1:
                    raise
                    
                # Exponential backoff for rate limits
                delay = self.retry_delay * (2 ** attempt)
                # LOGGER INFO logger.error(f"Rate limit hit, retrying in {delay}s")
                await asyncio.sleep(delay)

            except APIError as e:
                # LOGGER INFO logger.error(f"OpenAI API error: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)


            except Exception as e:
                # LOGGER INFO logger.error(f"Unexpected error generating embedding: {e}")
                if attempt < self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)

    async def generate_embeddings_batch(
        self, 
        texts: List[str]
        ) -> List[List[float]]:
        """
        Generate embeddings for a batch of texts

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """

        # Filter and truncate texts
        processed_texts = []
        for text in texts:
            if not text or not text.strip():
                processed_texts.append("")
                continue

            # Truncate if too long
            if len(text) > self.config["max_tokens"] * 4:
                text = text[:self.config["max_tokens"] * 4]
            processed_texts.append(text)
        
        for attempt in range(self.max_retries):
            try:
                response = await embedding_client.embeddings.create(
                    model=self.model,
                    input=processed_texts
                )
                return [data.embedding for data in response.data]
            
            except RateLimitError as e:
                if attempt == self.max_retries - 1:
                    raise
                    
                # Exponential backoff for rate limits
                delay = self.retry_delay * (2 ** attempt)
                # LOGGER INFO logger.error(f"Rate limit hit, retrying in {delay}s")
                await asyncio.sleep(delay)

            except APIError as e:
                # LOGGER INFO logger.error(f"OpenAI API error: {e}")
                if attempt == self.max_retries - 1:
                    # Fallback to indivual processing
                    return await self._process_individually(processed_texts)
                await asyncio.sleep(self.retry_delay)


            except Exception as e:
                # LOGGER INFO logger.error(f"Unexpected error generating embedding: {e}")
                if attempt < self.max_retries - 1:
                    return await self._process_individually(processed_texts)
                await asyncio.sleep(self.retry_delay)

    async def _process_individually(self, texts: List[str]) -> List[List[float]]:
        """ 
        Fallback method to process texts individually if batch processing fails

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        embeddings = []
        for text in texts:
            try: 
                if not text or not text.strip():
                    embeddings.append([0.0] * self.config["dimensions"])
                    continue

                embedding = await self.generate_embeddings(text)
                embeddings.append(embedding)

                # Small delay to avvoid overwhelming the API
                await asyncio.sleep(1)

            except Exception as e:
                # LOGGER INFO logger.error(f"Failed to generate embedding for text: {e}")
                # Use zero vector as fallback
                embeddings.append([0.0]*self.config["dimensions"])

        return embeddings

    async def embed_chunks(
        self,
        chunks: List[DocumentChunk],
        progress_callback: Optional[callable] = None
        ) -> List[Tuple[DocumentChunk, List[float]]]:
        """
        Generate embeddings for document chunks

        Args:
            chunks: List of DocumentChunk objects
            progress_callback: Optional callback to report progress
        
        Returns:
            Chunks with embedding model
        """

        if not chunks:
            return chunks
        
        embedded_chunks = []
        total_batches = (len(chunks) + self.batch_size - 1) // self.batch_size

        logger.info(f"Starting Embedding Process")

        for i in range(0, len(chunks), self.batch_size):
            batch_chunks = chunks[i:i + self.batch_size]
            batch_texts = [chunk.content for chunk in batch_chunks]

            try:
                # Generate embeddings for this batch
                embeddings = await self.generate_embeddings_batch(batch_texts)

                # Add embeddings to chunks
                for chunk, embedding in zip(batch_chunks, embeddings):
                    # Create a new chunk with embedding
                    embedded_chunk = DocumentChunk(
                        content=chunk.content,
                        index=chunk.index,
                        md=chunk.md,
                        metadata={
                            **chunk.metadata, 
                            "embedding_model": self.model,
                            "embedding_generated_at": datetime.now().isoformat()
                            },
                        token_count=chunk.token_count
                        )
                    # Add embedding as a separate attribute
                    embedded_chunk.embedding = embedding
                    embedded_chunks.append(embedded_chunk)

                # Progress Update
                current_batch = (i // self.batch_size) + 1
                if progress_callback:
                    progress_callback(current_batch, total_batches)
                    logger.info(f"Processed batch {current_batch}/{total_batches}")

            except Exception as e:   
                logger.error(f"Failed to process batch {(i // self.batch_size) + 1}: {e}")

                # Add chunks without embeddings as fallback
                for chunk in batch_chunks:
                    chunk.metadata.update(
                        {
                            "embedding_error": str(e),
                            "embedding_generated_at": datetime.now().isoformat()
                        }
                    )
                    chunk_embedding = [0.0] * self.config["dimensions"]
                    embedded_chunks.append(chunk)
            logger.info(f"Embedding generation completed with {len(embedded_chunks)} chunks.")
        return embedded_chunks

    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for search query

        Args:
            query: Query text to embed

        Returns:
            Query embedding vector
        """

        return await self.generate_embeddings(query)

    def get_embedding_dimensions(self) -> int:
        """ Get the number of dimensions for the embedding model """
        return self.config["dimensions"]


# Cache for embeddings
class EmbeddingCache:
    """ Simple in memory cache for embeddings """

    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, List[float]]={}
        self.access_times: Dict[str, datetime] = {}
        self.max_size = max_size
    
    def get(self, text: str) -> Optional[List[float]]:
        """ Get embedding from cache """
        text_hash = self._hash_text(text)

        if text_hash in self.cache:
            self.access_times[text_hash] = datetime.now()
            return self.cache[text_hash]
        return None

    def put(self, text: str, embedding: List[float]):
        """ Put/Store embedding in cache """
        text_hash = self._hash_text(text)

        # Evict oldest entries if cache is full
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
            del self.cache[oldest_key]
            del self.access_times[oldest_key]

        self.cache[text_hash] = embedding
        self.access_times[text_hash] = datetime.now()

    def _hash_text(self, text: str) -> str:
        """ Simple hash function for text """
        import hashlib
        return hashlib.sha256(text.encode('utf-8')).hexdigest()


# Factory funciion 
def create_embedder(
    model: str = EMBEDDING_MODEL,
    use_cache: bool = True,
    **kwargs
) -> EmbeddingGenerator:
    """
    Create embedding generator with optional caching

    Args:
        model: embedding model name
        use_cache: whether to use caching
        **kwargs: additional arguments for EmbeddingGenerator
     """
    embedder = EmbeddingGenerator(
        model = model,
        *kwargs
    )

    if use_cache:
        cache = EmbeddingCache()
        original_generate = embedder.generate_embeddings

        async def cached_generate(text: str) -> List[float]:
            cached = cache.get(text)
            if cached is not None:
                return cached
            
            embedding = await original_generate(text)
            cache.put(text, embedding)
            return embedding

        embedder.generate_embeddings = cached_generate

    return embedder


# Example usage
async def main():
    from .chunker import ChunkingConfig, create_chunker
    """ Example usage of EmbeddingGenerator """
    embedder = create_embedder(use_cache=True)
    config = ChunkingConfig(
        chunk_size=400,
    )
    chunker = create_chunker(config)

    chunks_document = "Your document text goes here. It can be very long and will be chunked accordingly."
    chunks = chunker.chunk_text(chunks_document) 

    def progress_callback(current, total):
        print(f"Embedding progress: {current}/{total} batches processed.")
    
    embedded_chunks = await embedder.embed_chunks(chunks, progress_callback=progress_callback)

    for chunk in embedded_chunks:
        print(f"Chunk index: {chunk.index}, Embedding length: {len(chunk.embedding)}")
        print(f"Chunk content: {chunk.content[:50]}...")  # Print first 50 characters

if __name__ == "__main__":
    asyncio.run(main())