"""
Knowledge graph builder for extracting entities and relationships.
"""
import asyncio
import json
import logging
import os
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone
import re
from collections import Counter

from dotenv import load_dotenv

import graphiti_core
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config_recipes import NODE_HYBRID_SEARCH_RRF
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from graphiti_core.search.search_config_recipes import (
    COMBINED_HYBRID_SEARCH_RRF,
    COMBINED_HYBRID_SEARCH_MMR,
    COMBINED_HYBRID_SEARCH_CROSS_ENCODER
)

from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge, EpisodicEdge

from graphiti_core.utils.maintenance import clear_data 

from neo4j import AsyncDriver

try:
    from  ..agent.graph_utils import GraphitiClient
    from  ..ingestion.data_prep import Item
except:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.graph_utils import GraphitiClient
    from ingestion.data_prep import Item


# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds knowledge graph from document items."""

    def __init__(self):
        self.graph_client = GraphitiClient()
        self._initialized = False

    async def initialize(self):
        """ Initialize the Graphiti client """
        if not self._initialized:
            await self.graph_client.initialize()
            self._initialized = True

    async def close(self):
        """ Close the Graphiti client connection """
        if self._initialized:
            await self.graph_client.close()
            self._initialized = False

    async def add_items_to_graph(
            self,
            items: List[Item],
            batch_size: int = 3,
            group_id: str = "default_client"

    ) -> Dict[str, Any]:
        """
        Add items to the knowledge graph in batches.

        Args:
            items: List of Item objects to add
            batch_size: Number of items to process in each batch
        Returns:
            Processing results
        """

        if not self._initialized:
            await self.initialize()

        if not items:
            return {"status": "no_items", "message": "No items provided."}
      

        title_counts = Counter(item.doc_title for item in items if hasattr(item, "doc_title") and item.doc_title)
        title_count_dict = []
        for i, (title, count) in enumerate(title_counts.items()):
            title_count_dict.append({"title": title, "count": count})
        j=0

   
        # Check for oversized items
        oversized_items = [i for i, item in enumerate(items) if len(item.md) > 10000]
        if len(oversized_items) > 0:
            logger.warning(f"{len(oversized_items)} items exceed the size limit and will be truncated {oversized_items}.")
        
        episodes_created = 0
        errors = []

        logger.info(f"START: Processing Document: {title_count_dict[j]["title"]} -  Adding {title_count_dict[j]["count"]} items to knowledge graph.")
        j+=1

        for i, item in enumerate(items):
            try:
                # Log when document title changes
                if i > 0 and items[i].doc_title != items[i - 1].doc_title:
                    logger.info(f"Processing Document: {title_count_dict[j]["title"]} -  Adding {title_count_dict[j]["count"]} items to knowledge graph.")
                    j+=1


                # Create unique episode ID
                episode_id = f"{item.doc_title}_{item.item_idx}_{datetime.now().timestamp()}"

                # Prepare episode content with size limits
                episode_content = self._prepare_episode_content(
                    item
                )

                source_description = f"Document: {item.doc_title}, Page: {item.page} " #(Item {item.item_idx}), Type: {item.type_item}"

                await self.graph_client.add_episodes(
                    episode_id=episode_id,
                    content=episode_content,
                    source=source_description,
                    client=group_id,
                    timestamp=datetime.now(timezone.utc),
                    metadata={
                        "document_title": item.doc_title,
                        "page": item.page,
                        "type": item.type_item,
                        "index": item.item_idx,
                        "document_source": item.file_path,
                        "original_length": len(item.md),
                        "processed_length": len(episode_content),
                    },
                )
                episodes_created += 1
                logger.info(f"Added episode {i+1}/{len(items)}:  {episode_id}")

                if i < len(items) - 1:
                    await asyncio.sleep(0.5)  # Small delay to avoid overwhelming the LLM API
            except Exception as e:
                error_msg = f"Failed to add item {i} to graph: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

                continue 
        result = {
            "episodes_created": episodes_created,
            "total_items": len(items),
            "errors": errors
        }

        logger.info(f"Graph building complete: {episodes_created}/{len(items)} episodes created, {len(errors)} errors.")

        return result
    
    def _prepare_episode_content(self, item: Item) -> str:
        """
        Prepare episode content by cleaning and truncating if necessary.

        Args:
            item: Item object containing content and metadata
        Returns:
            Formatted episode content (optimized for Graphiti)
        """
        max_content_length = 10000  # Max characters for episode content

        content = item.md

        if len(content) > max_content_length:
            truncated = content[:max_content_length]
            last_sentence_end = max(
                truncated.rfind('. '), truncated.rfind('! '), truncated.rfind('? ')
            )
            if last_sentence_end > max_content_length * 0.7: # if we can keep 70% and end cleanly
                content = truncated[:last_sentence_end + 1] + " [TRUNCATED]"
            else:
                content = truncated + " [TRUNCATED]"
            
            logger.warning(f"Content for item {item.index} truncated from {len(item.md)} to {len(content)} characters for Graphiti.")

        if item.doc_title and len(content) < max_content_length - 100:
            episode_content = f"[Doc: {item.doc_title[:50]}]\n\n{content}"
        else:
            episode_content = content

        return episode_content
    
    def _estimate_tokens(self, text: str) -> int:
        """ Rough estimate of token count based on character count """
        return len(text) / 4  # Approximation: 1 token ~ 4 characters
    
    def _is_content_too_large(self, content: str, max_tokens: int = 7000) -> bool:
        """ Check if content exceeds size limits """
        return self._estimate_tokens(content) > max_tokens

    async def clear_graph(self):
        """ Clear the entire knowledge graph """
        if not self._initialized:
            await self.initialize()
        logger.info("Clearing the entire knowledge graph...")
        try:
            await self.graph_client.clear_graph()
            logger.info("Knowledge graph cleared successfully.")
        
        except Exception as e:
            logger.error(f"Failed to clear knowledge graph: {e}")



# Factory function
def create_graph_builder() -> GraphBuilder:
    """ Factory function to create a GraphBuilder instance """
    builder = GraphBuilder()
    return builder
        
async def main():
    """ Example usage of GraphBuilder """
    graph_builder = create_graph_builder()

    # Example items to add
    items = [
        Item(
            doc_title="Sample Document",
            item_idx=0,
            md="This is a sample content for item 0.",
            page=1,
            type_item="text",
            file_path="/path/to/document.pdf"
        ),
        Item(
            doc_title="Sample Document",
            item_idx=1,
            md="This is a sample content for item 1.",
            page=1,
            type_item="text",
            file_path="/path/to/document.pdf"
        )
    ]
    # Add items to the graph
    try: 
        result = await graph_builder.add_items_to_graph(items)
    except Exception as e:
       logger.error(f"Error occurred while adding items to graph: {e}")

    finally:
        await graph_builder.close()

if __name__ == "__main__":
    asyncio.run(main())
