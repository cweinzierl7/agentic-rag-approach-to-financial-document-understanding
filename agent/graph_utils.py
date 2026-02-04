
"""
Graph utilities for Neo4j/Graphiti integration
"""

import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional, Tuple
import graphiti_core
from datetime import datetime, timezone


from dotenv import load_dotenv

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType
from graphiti_core.search.search_config import SearchConfig
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.llm_client.openai_client import OpenAIClient
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

from graphiti_core.search.search_config_recipes import (
    NODE_HYBRID_SEARCH_RRF,
    NODE_HYBRID_SEARCH_MMR,
    NODE_HYBRID_SEARCH_CROSS_ENCODER,
    EDGE_HYBRID_SEARCH_RRF,
    EDGE_HYBRID_SEARCH_MMR,
    EDGE_HYBRID_SEARCH_CROSS_ENCODER,
    COMBINED_HYBRID_SEARCH_RRF,
    COMBINED_HYBRID_SEARCH_MMR,
    COMBINED_HYBRID_SEARCH_CROSS_ENCODER
)

from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.edges import EntityEdge, EpisodicEdge

from graphiti_core.utils.maintenance import clear_data 



from neo4j import AsyncDriver

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class GraphitiClient: 
    """ Manages Graphiti knowledge graph operations"""

    def __init__(self,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None
        ):
        """ 
        Initialize Graphiti client with Neo4j connection parameters 
            Args:
                neo4j_uri: URI for Neo4j connection
                neo4j_user: Username for Neo4j connection
                neo4j_password: Password for Neo4j connection 
        """
        # Neo4j configuration
        self.neo4j_uri = neo4j_uri or os.getenv('NEO4J_URI', 'bolt://localhost:7687')
        self.neo4j_user = neo4j_user or os.getenv('NEO4J_USER', 'neo4j')
        self.neo4j_password = neo4j_password or os.getenv('NEO4J_PASSWORD')

        if not self.neo4j_password:
            raise ValueError('NEO4J_PASSWORD not set')
        
        # LLM configuration 
        self.llm_base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.llm_api_key = os.getenv("LLM_API_KEY")
        self.llm_choice = "gpt-4.1" # os.getenv("LLM_CHOICE_KG", "gpt-4.1")

        if not self.llm_api_key:
            raise ValueError('LLM_API_KEY not set')
        
        # Embedding configuration
        self.embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
        self.embedding_api_key = os.getenv("EMBEDDING_API_KEY")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.embedding_dimensions = int(os.getenv("VECTOR_DIMENSION", "1536"))

        if not self.embedding_api_key:
            raise ValueError('EMBEDDING_API_KEY not set')
        
        self.graphiti: Optional[Graphiti] = None
        self._initialized = False

    async def initialize(self):
        """ Initialize the Graphiti client and connect to Neo4j """
        if self._initialized:
            return
        
        try: 
            # Create LLMConfig
            llm_config = LLMConfig(
                api_key=self.llm_api_key,
                base_url=self.llm_base_url,
                model=self.llm_choice,
                small_model = self.llm_choice # can be the same as main model
            )


            embedder_config = OpenAIEmbedderConfig(
                api_key=self.embedding_api_key,
                base_url=self.embedding_base_url,
                embedding_model=self.embedding_model)
            

            # Initialize Graphiti with custom clients
            self.graphiti = Graphiti(
                self.neo4j_uri,
                self.neo4j_user,
                self.neo4j_password,
                llm_client=OpenAIGenericClient(config=llm_config),
                embedder=OpenAIEmbedder(
                config=embedder_config,
                #dimensions=self.embedding_dimensions
                ),
                cross_encoder=OpenAIRerankerClient(
                    config = LLMConfig(
                        api_key=self.llm_api_key,
                        base_url=self.llm_base_url,
                        model=self.llm_choice,
                    )
                )
            )

            # Build indices and constraints 
            await self.graphiti.build_indices_and_constraints()
            self._initialized = True
            logger.info(f"Graphiti client initialized successfully with LLM: {self.llm_choice} and embedder: {self.embedding_model}")

        except Exception as e:
            logger.error(f"Failed to initialize Graphiti client: {e}")
            raise
    
    async def close(self):
        """ Close the Graphiti client connection """
        if self.graphiti:
            await self.graphiti.close()
            self.graphiti = None
            self._initialized = False
            logger.info("Graphiti client connection closed.")

    
    async def add_episodes(
            self,
            episode_id: str,
            content: str,
            source: str,
            client: Optional[str] = None,
            group_id: Optional[str] = None,
            timestamp: Optional[datetime] = None,
            metadata: Optional[Dict[str, Any]] = None,
            
    ):
        """
        Add an episode to the knowledge graph
        """
        if not self._initialized or not self.graphiti:
            await self.initialize()

        episode_timestamp = timestamp or datetime.now(timezone.utc)

        # Backwards-compatible parameter handling.
        if client is None:
            client = group_id
        if client is None:
            raise ValueError("Either 'client' or 'group_id' must be provided")

        from graphiti_core.nodes import EpisodeType

        await self.graphiti.add_episode(
            name=episode_id,
            episode_body = content,
            source = EpisodeType.text, # always use text type for our content
            source_description = source,
            reference_time = episode_timestamp,
            group_id=client,
            
                )
        

        # logger.info(f"Added episode '{episode_id}' to knowledge graph.")
    
    async def search(
            self,
            query: str, 
            reranker: str = "RRF",
            group_id: Optional[List[str]] = None,
            center_node_uuid: Optional[str] = None,
            limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search the knowledge graph for relevant episodes

        Args:
            query: The search query
            reranker: The re-ranking strategy to use (RRF, MMR, CrossEncoder)
        Returns:
            List of search results with episode details
        """

        if not self._initialized or not self.graphiti:
            await self.initialize()
        

        search_config = COMBINED_HYBRID_SEARCH_RRF.model_copy(deep=True) if reranker == "RRF" else COMBINED_HYBRID_SEARCH_MMR.model_copy(deep=True) if reranker == "MMR" else COMBINED_HYBRID_SEARCH_CROSS_ENCODER.model_copy(deep=True)  
        search_config.limit = limit
        try: 
            results = await self.graphiti._search(
            query=query,
            config=search_config,
            group_id=group_id
            )


            edges = dict(results).get("edges", [])
            edges_scores = dict(results).get("edge_reranker_scores", [])

            nodes = dict(results).get("nodes", [])
            nodes_scores = dict(results).get("node_reranker_scores", [])

            episodes = dict(results).get("episodes", [])
            episode_scores = dict(results).get("episode_reranker_scores", [])



            results_combined_dict = {
                "edges": [],
                "nodes": [],
                "episodes": []
            }

            for idx, edge in enumerate(edges):
                doc_source = await self._get_episode_metadata_by_facts(edge)
                edge_item = {
                    "fact": edge.fact,
                    "uuid": str(edge.uuid),
                    "valid_at": str(edge.valid_at) if hasattr(edge, "valid_at") and edge.valid_at else None,
                    "invalid_at": str(edge.invalid_at) if hasattr(edge, "invalid_at") and edge.invalid_at else None,
                    "source_node_uuid": str(edge.source_node_uuid) if hasattr(edge, "source_node_uuid") and edge.source_node_uuid else None,
                    "target_node_uuid": str(edge.target_node_uuid) if hasattr(edge, "target_node_uuid") and edge.target_node_uuid else None,
                    "episode_uuids": [str(epi_uuid) for epi_uuid in edge.episodes] if hasattr(edge, "episodes") else [],
                    "document_sources": doc_source,
                    "score_edge": edges_scores[idx] if idx < len(edges_scores) else None
                }
                results_combined_dict["edges"].append(edge_item)

            for idx, node in enumerate(nodes):
                doc_source = await self._get__metadata_by_nodes(node)
                node_item = {
                    "name": node.name,
                    "uuid": str(node.uuid),
                    "summary": node.summary,
                    "document_sources": doc_source,
                    "score_node": nodes_scores[idx] if idx < len(nodes_scores) else None
                }
                results_combined_dict["nodes"].append(node_item)

            for idx, episode in enumerate(episodes):
                episode_item = {
                    "content": episode.content,
                    "uuid": str(episode.uuid),
                    "valid_at": str(episode.valid_at) if hasattr(episode, "valid_at") and episode.valid_at else None,
                    "invalid_at": str(episode.invalid_at) if hasattr(episode, "invalid_at") and episode.invalid_at else None,
                    "source_description": episode.source_description,
                    "entity_edges": [str(edge_uuid) for edge_uuid in episode.entity_edges],
                    "score_episode": episode_scores[idx] if idx < len(episode_scores) else None
                }
                results_combined_dict["episodes"].append(episode_item)

            return results_combined_dict 

        except Exception as e:
            logger.error(f"Graph Search failed: {e}")
            return []
        
    async def search_facts(
            self, 
            query: str,
            reranker: str = "RRF",
            center_node_uuid: Optional[str] = None,
            group_id: Optional[List[str]] = None,
            limit: int = 10
    ):
        """
        Simple search wrapper returning only edges content - default Graphiti search
        EDGE_EDGE_HYBRID_SEARCH_RRF

        Args:
            query: The search query

        Optional Parameters:
            center_node_uuid: str, optional
            Facts will be reranked based on proximity to this node
            group_id : list[str | None] | None, optional
                The graph partitions to return data from, here client.
            Limit : int, optional
                The maximum number of results to return. Defaults to 10.
        Returns:
            List of edges contents
        """

        if not self._initialized or not self.graphiti:
            await self.initialize()
        
        try: 
            if reranker == "MMR":
                search_config = EDGE_HYBRID_SEARCH_MMR.model_copy(deep=True)
                search_config.limit = limit
                results = await self.graphiti._search(
                query=query,
                config=search_config,
                group_ids=group_id
                )
            elif reranker == "CrossEncoder":
                search_config = EDGE_HYBRID_SEARCH_CROSS_ENCODER.model_copy(deep=True)
                search_config.limit = limit
                results = await self.graphiti._search(
                query=query,
                config=search_config,
                group_ids=group_id
                )
            else:
                if reranker != "RRF": logger.warning(f"Unknown reranker '{reranker}', defaulting to RRF.")
                search_config = EDGE_HYBRID_SEARCH_RRF.model_copy(deep=True)
                search_config.limit = limit
                results = await self.graphiti._search(
                query=query,
                center_node_uuid=center_node_uuid,
                group_ids=group_id,
                config=search_config
                )

            facts = []
            scores = results.edge_reranker_scores if hasattr(results, "edge_reranker_scores") else []
            for idx, result in enumerate(results.edges): 
                doc_source = await self._get_episode_metadata_by_facts(result)
                fact = {
                        "fact": str(result.fact),
                        "uuid": str(result.uuid),
                        "valid_at": str(result.valid_at) if hasattr(result, "valid_at") and result.valid_at else None,
                        "invalid_at": str(result.invalid_at) if hasattr(result, "invalid_at") and result.invalid_at else None,
                        "source_node_uuid": str(result.source_node_uuid) if hasattr(result, "source_node_uuid") and result.source_node_uuid else None,
                        "target_node_uuid": str(result.target_node_uuid) if hasattr(result, "target_node_uuid") and result.target_node_uuid else None,
                        "episode_uuids": [str(epi_uuid) for epi_uuid in result.episode_uuids] if hasattr(result, "episode_uuids") else [],
                        "document_sources": doc_source,
                        "score": scores[idx] if idx < len(scores) else None
                    }
                facts.append(fact)
            return facts


        except Exception as e:
            logger.error(f"Graph Fact Search failed: {e}")
            return []

    async def search_entities(
            self, 
            query: str,
            reranker: str = "RRF",
            center_node_uuid: Optional[str] = None,
            group_id: Optional[List[str]] = None,
            limit: int = 10
    ):
        """
        Simple search wrapper returning nodes content 

        Args:
            query: The search query
            reranker: The re-ranking strategy to use (RRF, MMR, CrossEncoder)

        Returns:
            List of nodes contents
        """

        if not self._initialized or not self.graphiti:
            await self.initialize()
        

        try: 
            if reranker == "MMR":
                search_config = NODE_HYBRID_SEARCH_MMR.model_copy(deep=True)
                search_config.limit = limit
   
            elif reranker == "CrossEncoder":
                search_config = NODE_HYBRID_SEARCH_CROSS_ENCODER.model_copy(deep=True)
                search_config.limit = limit
            
            elif reranker == "NodeDistance" and center_node_uuid is not None:
                search_config = NODE_HYBRID_SEARCH_NODE_DISTANCE.model_copy(deep=True)
                search_config.limit = limit

                results = await self.graphiti._search(
                query=query,
                config=search_config,
                center_node_uuid=center_node_uuid,
                group_ids=group_id
                )
                
            else:
                if reranker != "RRF": logger.warning(f"Unknown reranker '{reranker}', defaulting to RRF.")
                search_config = NODE_HYBRID_SEARCH_RRF.model_copy(deep=True)
                search_config.limit = limit
                
            if center_node_uuid is None: 
                
                results = await self.graphiti._search(
                query=query,
                config=search_config,
                group_ids=group_id
                )
            
            nodes = []
            scores = results.node_reranker_scores if hasattr(results, "node_reranker_scores") else []
            for idx, result in enumerate(results.nodes): 
                doc_source = await self._get__metadata_by_nodes(result)
                node = {
                        "name": result.name,
                        "uuid": str(result.uuid),
                        "summary": result.summary,
                        "document_sources": doc_source,
                        "score": scores[idx] if idx < len(scores) else None
                    }
                nodes.append(node)
            return nodes

        except Exception as e:
            logger.error(f"Graph Entity Search failed: {e}")
            return []

    async def clear_graph(self):
        """ Clear all data from the knowledge graph """
        if not self._initialized:
            await self.initialize()
        
        try:
            await clear_data(self.graphiti.driver)
            logger.info("Knowledge graph cleared successfully.")
        except Exception as e:
            logger.error(f"Failed to clear knowledge graph using clear_data: {e}")
            
            # Fallback: Close and re-initialize the database
            if self.graphiti:
                await self.graphiti.close()
                
                llm_config = LLMConfig(
                    api_key=self.llm_api_key,
                    base_url=self.llm_base_url,
                    model=self.llm_choice,
                    small_model = self.llm_choice # can be the same as main model
                )

                # create OpenAI LLM client
                llm_client = OpenAIClient(config=llm_config)

                embedder_config = OpenAIEmbedderConfig(
                    api_key=self.embedding_api_key,
                    base_url=self.embedding_base_url,
                    embedding_model=self.embedding_model
                    )

                # create OpenAI embedder
                embedder = OpenAIEmbedder(
                    config=embedder_config,
                    #dimensions=self.embedding_dimensions
                )

                # Initialize Graphiti with custom clients
                self.graphiti = Graphiti(
                    self.neo4j_uri,
                    self.neo4j_user,
                    self.neo4j_password,
                    llm_client=llm_client,
                    embedder=embedder,
                    cross_encoder=OpenAIRerankerClient(client=llm_client, config=llm_config)
                )

                # Build indices and constraints 
                await self.graphiti.build_indices_and_constraints()
                logger.info("Graphiti client re-initialized successfully after fallback.")

    async def _get_episode_metadata_by_facts(self, edge_item: EntityEdge)-> str:
        """
        Retrieve episodes related to given facts

        Args:
            edge_item: The EntityEdge item containing episode UUIDs
        Returns:
            Source descriptions of related episodes
        """
        episode_uuids = edge_item.episodes if hasattr(edge_item, "episodes") else []
        try: 
            results_episodes =  await EpisodicNode.get_by_uuids(self.graphiti.driver, episode_uuids)
            source_description = [result.source_description for result in results_episodes]


            titles_pages = ""
            title_previous = ""

            for line in source_description:
                split_idx = line.lower().find("page")
                if split_idx != -1:
                    title = line[:split_idx].rstrip()
                    page = line[split_idx:].lstrip()
                else:
                    title = line
                    page = ""
                if title != title_previous: titles_pages += f"{title} {page}; "
                else: titles_pages += f"{page}; "
                title_previous = title
            return titles_pages 
        
        except Exception as e:
            logger.error(f"Failed to retrieve episodes for edge {edge_item.uuid}: {e}")
            return []

    async def _get__metadata_by_nodes(self, node_item: EntityNode)-> str:
        """
        Retrieve episodes related to given nodes

        Args:
            node_item: The EntityNode item containing episode UUIDs
        Returns:
            Source descriptions of related episodes
        """
        node_uuid = node_item.uuid 
        try: 
            results_episodes =  await EpisodicNode.get_by_entity_node_uuid(self.graphiti.driver, node_uuid)
            source_description = [result.source_description for result in results_episodes]

            titles_pages = ""
            title_previous = ""

            for line in source_description:
                split_idx = line.lower().find("page")
                if split_idx != -1:
                    title = line[:split_idx].rstrip()
                    page = line[split_idx:].lstrip()
                else:
                    title = line
                    page = ""
                if title != title_previous: titles_pages += f"{title} {page}; "
                else: titles_pages += f"{page}; "
                title_previous = title
            return titles_pages 
        
        except Exception as e:
            logger.error(f"Failed to retrieve episodes for node {node_item.uuid}: {e}")
            return []
        
    async def get_graph_statistics(self) -> Dict[str, Any]:
        """
        Get basic statistics about the knowledge graph.
        
        Returns:
            Graph statistics
        """
        if not self._initialized:
            await self.initialize()
        
        # For now, return a simple search to verify the graph is working
        # More detailed statistics would require direct Neo4j access
        try:
            test_results = await self.graphiti.search("test")
            return {
                "graphiti_initialized": True,
                "sample_search_results": len(test_results),
                "note": "Detailed statistics require direct Neo4j access"
            }
        except Exception as e:
            return {
                "graphiti_initialized": False,
                "error": str(e)
            }
    
                    

    



# graph statistics function

# entity timeline function

# related entity retrieval function


# Global Graphiti client instance
graph_client = GraphitiClient()


async def initialize_graph():
    """Initialize graph client."""
    await graph_client.initialize()

async def search_knowledge_graph_facts(
    query: str,
    group_id: List[str],
    limit: int,
    reranker: str = "RRF",
) -> List[Dict[str, Any]]:
    """
    Search the knowledge graph for facts.
    
    Args:
        query: Search query
    
    Returns:
        Search results
    """
    return await graph_client.search_facts(query=query, group_id=group_id, reranker=reranker, limit=limit)

async def search_knowledge_graph_entities(
    query: str,
    limit: int,
    group_id:   List[str],
    reranker: str = "RRF",
    center_node_uuid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
    """
    Search the knowledge graph for entities.
    
    Args:
        query: Search query
    
    Returns:
        Search results
    """
    return await graph_client.search_entities(query=query, group_id=group_id, reranker=reranker, center_node_uuid=center_node_uuid, limit=limit)


async def close_graph():
    """Close graph client."""
    await graph_client.close()

async def test_graph_connection() -> bool:
    """
    Test graph database connection.
    
    Returns:
        True if connection successful
    """
    try:
        await graph_client.initialize()
        stats = await graph_client.get_graph_statistics()
        logger.info(f"Graph connection successful. Stats: {stats}")
        return True
    except Exception as e:
        logger.error(f"Graph connection test failed: {e}")
        return False
