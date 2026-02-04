"""
Tools for the agents
"""

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .graph_utils import (
    search_knowledge_graph_entities,
    search_knowledge_graph_facts,
    graph_client
)

from .vector_db_utils import (
    search_hybrid,
    weaviate_client,
    search_vector
)

from .providers import get_embedding_client, get_embedding_model

from .models import (
    GraphSearchCombiResult,
    GraphSearchFactResult,
    GraphSearchEntityResult,
    VectorHybridResult,
    VectorResult
)


# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


embedding_client = get_embedding_client()
EMBEDDING_MODEL = get_embedding_model()


async def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding for text using OpenAI.
    
    Args:
        text: Text to embed
    
    Returns:
        Embedding vector
    """
    try:
        response = await embedding_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {e}")
        raise



# Tool Input Models
class HybridSearchInput(BaseModel):
    """Input for hybrid search tool."""
    query: str = Field(..., description="Search query")
    client: str = Field(default="default_client", description="Client identifier for filtering results")
    limit: Optional[int] = Field(default=20, description="Maximum number of results")
    weight_alpha: Optional[float] = Field(default=0.75, description="Ratio between keyword and vector search (0-1)")
    fusion_type: Optional[str] = Field(default="HybridFusion.RELATIVE_SCORE", description="Type of fusion for hybrid search"),
    k: Optional[int] = Field(default=0, description="Number of chunks to include before and after each matched chunk")

class GraphSearchInput(BaseModel):
    """Input for graph search tool."""
    query: str = Field(..., description="Search query")
    group_id: str = Field(default="default_client", description="Group ID for filtering results -- e.g., client identifier")
    reranker_entity: Optional[str] = Field(default="RRF", description="Reranker model to use for entities")
    reranker_fact: Optional[str] = Field(default="RRF", description="Reranker model to use for facts")
    limit_fact: Optional[int] = Field(default=10, description="Maximum number of results for graph search")
    limit_entity: Optional[int] = Field(default=10, description="Maximum number of results for graph search")
    

class VectorSearchInput(BaseModel):
    """Input for vector search tool."""
    query: str = Field(..., description="Search query")
    client: str = Field(default="default_client", description="Client identifier for filtering results")
    limit: Optional[int] = Field(default=20, description="Maximum number of results")
    k: Optional[int] = Field(default=0, description="Number of chunks to include before and after each matched chunk")


async def graph_search_tool_facts(input_data: GraphSearchInput) -> List[GraphSearchFactResult]:
    """
    Search the knowledge graph.
    
    Args:
        input_data: Search parameters
    
    Returns:
        List of graph search results
    """
    try:
        group_id_list = input_data.group_id if isinstance(input_data.group_id, list) else [input_data.group_id]
        results_facts = await search_knowledge_graph_facts(
            query=input_data.query,
            group_id=group_id_list,
            reranker=input_data.reranker_fact,
            limit=input_data.limit_fact
        )
        
        # Convert to GraphSearchResult models
        result_facts_dict = [GraphSearchFactResult(
                    fact=r["fact"],
                    uuid=r["uuid"],
                    valid_at=r.get("valid_at"),
                    invalid_at=r.get("invalid_at"),
                    source_node_uuid=r.get("source_node_uuid"),
                    target_node_uuid=r.get("target_node_uuid"),
                    episode_uuids=r.get("episode_uuids", []),
                    document_sources=r.get("document_sources", []),
                    score=r.get("score", None)
                )
                for r in  results_facts
            ]
        return result_facts_dict
        
    except Exception as e:
        logger.error(f"Graph search failed: {e}")
        return []
    

async def graph_search_tool_entities(input_data: GraphSearchInput) -> List[GraphSearchEntityResult]:
        
    try:
        group_id_list = input_data.group_id if isinstance(input_data.group_id, list) else [input_data.group_id]
        results_entities = await search_knowledge_graph_entities(
            query=input_data.query,
            group_id=group_id_list,
            reranker=input_data.reranker_entity,
            limit=input_data.limit_entity
        )
            
        result_entities_dict = [GraphSearchEntityResult(
                name=r["name"],
                uuid=r["uuid"],
                summary=r["summary"],
                document_sources=r.get("document_sources", []),
                score=r.get("score", None)
            )
            for r in results_entities
            ]
        return result_entities_dict
    except Exception as e:
        logger.error(f"Graph search failed: {e}")
        return []
    

async def vector_hybrid_search_tool(input_data: HybridSearchInput) -> List[VectorHybridResult]:
    """
    Perform hybrid vector search.
    
    Args:
        input_data: Search parameters
    
    Returns:
        List of search results
    """
    try:

        results = await search_hybrid(
            query=input_data.query,
            alpha=input_data.weight_alpha,
            limit=input_data.limit,
            fusion_type=input_data.fusion_type,
            client=input_data.client,
            k = input_data.k
        )

        results_vectorhybrid = [VectorHybridResult(
                title=r["title"],
                page=r["page"],
                content=r["content"],
                score=r["score"],
                table_md=r.get("table_md")
            )
            for r in results
            ]
        return results_vectorhybrid
    except Exception as e:
        logger.error(f"Hybrid vector search failed: {e}")
        return []
    

async def vector_search_tool(input_data: VectorSearchInput) -> List[VectorResult]:
    """
    Perform vector search.
    
    Args:
        input_data: Search parameters
    
    Returns:
        List of search results
    """
    try:

        results = await search_vector(
            query=input_data.query,
            limit=input_data.limit,
            client=input_data.client,
            #k=input_data.k
        )

        results_vector = [VectorHybridResult(
                title=r["title"],
                page=r["page"],
                content=r["content"],
                score=r["score"],
                table_md=r.get("table_md"),
                distance = r["distance"]
            )
            for r in results
            ]
        return results_vector
    except Exception as e:
        logger.error(f"Hybrid vector search failed: {e}")
        return []