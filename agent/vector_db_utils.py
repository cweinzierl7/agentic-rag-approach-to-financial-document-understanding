"""
Vector DB Utilities for Weaviate
"""
import asyncio
import json
import logging
import os
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime, timezone
import re

from dotenv import load_dotenv

from ingestion.embedder import create_embedder

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Property, DataType, Configure, VectorDistances, ReferenceProperty
from weaviate.util import generate_uuid5  # Generate a deterministic 
from weaviate.classes.init import Auth
from weaviate.classes.data import DataReference
from weaviate.classes.query import HybridFusion, Filter, QueryReference


# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)




class VectorDB_Schema:
    """ Class to handle Weaviate vector database operations """

    def __init__(self, class_chunk: str = "Chunks", class_fulldoc: str = "FullDoc"):
        self.client: Optional[weaviate.Client] = None
        self.class_chunk = class_chunk
        self.class_fulldoc = class_fulldoc
        self._initialized = False


    def initialize_database(self, basis: str = "local"):
        ''' 
            Initialize Weaviate database

            Args: 
                basis (str): The basis for the database connection ("local" or "cloud").
            Returns:
                client: Weaviate client instance
        '''
        if self._initialized:
            return 
        
        try: 
            if basis == "local":
                self.client = weaviate.connect_to_local()
                self._initialized = True
                logger.info("Weaviate client initialized for local instance.")
        
            elif basis == "cloud":
                WEAVIATE_URL = os.getenv("WEAVIATE_URL", "")
                WEAVIATE_API = os.getenv("WEAVIATE_API", "")
                self.client = weaviate.connect_to_weaviate_cloud(
                    cluster_url=WEAVIATE_URL,
                    auth_credentials=Auth.api_key(WEAVIATE_API),
                )
                self._initialized = True
                logger.info("Weaviate client initialized for cloud instance.")
            else:
                raise ValueError("No initialization possible.")
        except Exception as e:
            logger.error(f"Failed to initialize Weaviate client: {e}")
            raise

        if self._initialized:
            self.ensure_class_exists_chunks()
            self.ensure_class_exists_fulldoc()

    def close_database(self):
        ''' 
            Close Weaviate database connection
        '''
        self.client.close()
        self._initialized = False
        logger.info("Weaviate client connection closed.")

    def ensure_class_exists_chunks(self):
        """ Ensure the Weaviate class schema exists """
        if not self.client.collections.exists(self.class_chunk):
            chunks_collection = self.client.collections.create(
                name = self.class_chunk,
                description= "A chunk of text from a document with embeddings",
                properties=[
                    Property(name="index", data_type=DataType.INT),
                    Property(name="title", data_type=DataType.TEXT),
                    Property(name="source", data_type=DataType.TEXT),
                    Property(name = "page", data_type=DataType.INT),
                    Property( name = "type", data_type=DataType.TEXT),
                    Property(name =  "heading_lvl1", data_type=DataType.TEXT),
                    Property(name =  "heading_lvl2", data_type=DataType.TEXT),
                    Property( name = "heading_lvl3", data_type=DataType.TEXT),
                    Property(name="content", data_type=DataType.TEXT),
                    Property(name="md", data_type=DataType.TEXT),
                    Property(name="client", data_type=DataType.TEXT),
                ],
                references =[
                    ReferenceProperty(
                                name = "document",
                                target_collection = "FullDoc"
                            )
                        ],
                vector_config=wvc.config.Configure.Vectors.self_provided(
                    vector_index_config=Configure.VectorIndex.hnsw(
                    distance_metric=VectorDistances.COSINE,  # options: cosine, dot, l2-squared
                )
                )
            )   
            return chunks_collection
        else:
            logger.info(f"Class '{self.class_chunk}' already exists.")

    def ensure_class_exists_fulldoc(self):
            if not self.client.collections.exists(self.class_fulldoc):
        # Create the collection. Weaviate's autoschema feature will infer properties when importing.
                full_doc_collection = self.client.collections.create(
                    name = self.class_fulldoc,
                    description="Full Document Storage",
                    properties=[
                        Property(name="title", data_type=DataType.TEXT),
                        Property(name="source", data_type=DataType.TEXT),
                        Property(name="md", data_type=DataType.TEXT),
                        Property(name="client", data_type=DataType.TEXT),
                    ],
                    
                    vector_config=wvc.config.Configure.Vectors.self_provided(),
                    
                )
                return full_doc_collection
            else:
                logger.info(f"Class '{self.class_fulldoc}' already exists.")


    def clean_collections(self):
        """ Clean up existing collections """
        if self.client.collections.exists(self.class_chunk):
            self.client.collections.delete(self.class_chunk)
            logger.info(f"Deleted collection '{self.class_chunk}'")
            self.ensure_class_exists_chunks()
        if self.client.collections.exists(self.class_fulldoc):
            self.client.collections.delete(self.class_fulldoc)
            logger.info(f"Deleted collection '{self.class_fulldoc}'")
            self.ensure_class_exists_fulldoc()

    async def hybrid_search(self, 
                        query: str, 
                        alpha: float = 0.5, 
                        limit: int = 15, 
                        fusion_type = HybridFusion.RELATIVE_SCORE,
                        client: Optional[List[str]] = None
                        ) -> Dict[str, Any]:
        """ Perform hybrid search 
        Args:
            query (str): The search query.
            alpha (float): Weighting factor between keyword and vector search.
            limit (int): Maximum number of results to return.
            fusion_type: Type of fusion for hybrid search.
            client (Optional[List[str]]): Client filter for the search.
        Returns:
            Search results."""
        embedder = create_embedder()

        if not self._initialized or not self.client:
            self.initialize_database()

        fulldoc_collection = self.client.collections.use(self.class_fulldoc)
        chunks_collection = self.client.collections.use(self.class_chunk)


        query_vector = await embedder.embed_query(query)


        response = chunks_collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=alpha,
            limit=limit,
            fusion_type = fusion_type,
            filters = wvc.query.Filter.by_property("client").equal(client),
            query_properties=["content^2", "md^2", "heading_lvl1", "heading_lvl2", "heading_lvl3", "title"],
            return_metadata=wvc.query.MetadataQuery(score=True, explain_score=True)
        )

        result_dict = [
            {   "chunk_index": o.properties["index"],
                "title": o.properties["title"],
                "page": o.properties["page"],
                "content": o.properties["content"],
                "table_md": o.properties["md"] if o.properties["type"] == "table" else None,
                "score": o.metadata.score,
                "explain_score": o.metadata.explain_score
            }
            for o in response.objects
        ]
        #logger.info(f"Hybrid search returned {len(result_dict)} results.")

        return result_dict
    
    async def vector_search(self, 
                        query: str, 
                        limit: int = 10, 
                        client: Optional[List[str]] = None
                        ) -> Dict[str, Any]:
        """ Perform vector search 
        Args:
            query (str): The search query.
            limit (int): Maximum number of results to return.
            client (Optional[List[str]]): Client filter for the search.
        Returns:
            Search results."""
        embedder = create_embedder()

        if not self._initialized or not self.client:
            self.initialize_database()

        fulldoc_collection = self.client.collections.use(self.class_fulldoc)
        chunks_collection = self.client.collections.use(self.class_chunk)


        query_vector = await embedder.embed_query(query)


        response = chunks_collection.query.near_vector(
            query=query,
            near_vector=query_vector,
            limit=limit,
            filters = wvc.query.Filter.by_property("client").equal(client),
            return_metadata=wvc.query.MetadataQuery(score=True, explain_score=True, distance=True)
        )

        result_dict = [
            {   "chunk_index": o.properties["index"],
                "title": o.properties["title"],
                "page": o.properties["page"],
                "content": o.properties["content"],
                "table_md": o.properties["md"] if o.properties["type"] == "table" else None,
                "score": o.metadata.score,
                "explain_score": o.metadata.explain_score,
                "distance":  o.metadata.distance,
            }
            for o in response.objects
        ]

        return result_dict
    
    def search_sentence_window_retrieval(self, search_result: List[Dict[str, Any]],
                                        k=3, client: Optional[List[str]] = None ) -> List[Dict[str, Any]]:
        """
        Search with window retrieval around matched chunks.

        Args:
            search_result: The search result object from Weaviate
            k: Number of chunks to include before and after each matched chunk

        """
        if not self._initialized or not self.client:
            self.initialize_database()

        fulldoc_collection = self.client.collections.use(self.class_fulldoc)
        chunks_collection = self.client.collections.use(self.class_chunk)

        # store indexes 
        index_base = [o["chunk_index"] for o in search_result]
    
        # expand each base index by +/- k and include all intermediate numbers (unique & sorted)
        indexes_to_retrieve = sorted({
        j
        for base in index_base
        for j in range(max(0, base - k), base + k + 1)
        })

        limit = (k*2 +1) * len(index_base)

        # retrieve all chunks within the index window

        responses_window_retrieval = chunks_collection.query.fetch_objects(
            limit=limit,
            filters=(
                Filter.by_property("index").contains_any(indexes_to_retrieve) & 
                Filter.by_property("client").equal(client) 
            )
        )

        # only keep those within the +/- k of base indexes and same page
        responses_window_retrieval.objects.sort(key=lambda o: o.properties.get("index", 0))


        page_index = []
        for object in responses_window_retrieval.objects:
            if object.properties["index"] in index_base:
                page_index.append(object.properties["page"])

        index_to_retrieve_set = []
        # check if object's index is within +/- k of any base index
        for idx, base in enumerate(sorted(index_base)):
            for object in responses_window_retrieval.objects:
                obj_idx = object.properties.get("index", None)
                if obj_idx is not None and obj_idx in range(base - k, base + k + 1):
                    if object.properties["page"] == page_index[idx]:
                        index_to_retrieve_set.append(object.properties["index"])

        # merge the consecutive chunks with same title & page
        merged = []
        for o in responses_window_retrieval.objects:
            idx = o.properties.get("index", 0)
            title = o.properties.get("title")
            page = o.properties.get("page")
            content = o.properties.get("content", "") or ""
            md = o.properties.get("md", "") or ""
            type_prop = o.properties.get("type", "")

            score = next((r["score"] for r in search_result if r["chunk_index"] == idx), None)
        
            explain_score = next((r["explain_score"] for r in search_result if r["chunk_index"] == idx), None)

            if idx not in index_to_retrieve_set:
                continue

            if merged:
                last = merged[-1]
                # check consecutive index and same title & page
                if idx == last["end_index"] + 1 and title == last["title"] and page == last["page"]:
                    # merge into last
                    last["end_index"] = idx
                    # Append content: if last has no content, set it; if content starts with '.' (ignoring leading whitespace) append directly,
                    # otherwise add a space between.
                    if content and content.lstrip().startswith("."):
                        last["content"] += content
                    else:
                        last["content"] += " " + content
                    # merge markdown if present
                    if md and type_prop == "table":
                        last["md"] += "\n\n" + md if last["md"] else md
                    # combine type labels (avoid duplicates)
                    combined_types = set(t.strip() for t in (last["type"] or "").split(",") if t.strip()) | set(t.strip() for t in (type_prop or "").split(",") if t.strip())
                    last["type"] = ", ".join(sorted(combined_types)) if combined_types else last["type"]

                    if idx in index_base:
                        last["score"] = float(score) if score is not None else last.get("score", None)
                        last["explain_score"] = explain_score if explain_score is not None else last.get("explain_score", None)
                    continue

            # otherwise start a new merged item
            

            merged.append({
                "start_index": idx,
                "end_index": idx,
                "title": title,
                "page": page,
                "content": content,
                "md": md if type_prop == "table" else "",
                "type": type_prop,
                "score": score,
                "explain_score": explain_score
                  })


            # get in shape
            result_dict = [
        {
                "title": o["title"],
                "page": o["page"],
                "content": o["content"],
                "table_md": o["md"],
                "score": o["score"],
                "explain_score": o["explain_score"]
            }
            for o in merged
        ]
        #logger.info(f"Sentence Window Retrieval  returned {len(result_dict)} results.")
        return result_dict



# Global instance
weaviate_client = VectorDB_Schema()

def initialize_database():
    ''' 
        Initialize Weaviate database
    '''
    weaviate_client.initialize_database()
    
        
def close_database():
    ''' 
        Close Weaviate database connection
    '''
    weaviate_client.close_database()


async def search_hybrid(
    query: str,
    limit: int = 10,
    alpha: float = 0.75,
    fusion_type: Optional[str] = None,
    client: Optional[str] = None, 
    k: Optional[int] = 0, 
) -> List[Dict[str, Any]]:
    """
    Perform a hybrid search on the vector database.
    """
    search_result =  await weaviate_client.hybrid_search(
        query=query,
        alpha=alpha,
        limit=limit,
        fusion_type=fusion_type,
        client=client
    )
    if k and k > 0:
        search_result_window = weaviate_client.search_sentence_window_retrieval(
            search_result=search_result,
            k=k,
            client=client
        )
        return search_result_window
    return search_result



async def search_vector(
    query: str,
    limit: int = 10,
    client: Optional[str] = None,
    k: Optional[int] = 0,
) -> List[Dict[str, Any]]:
    """
    Perform a vector search on the vector database.
    """
    search_result =  await weaviate_client.vector_search(
        query=query,
        limit=limit,
        client=client
    )
    if k and k > 0:
        search_result_window = weaviate_client.search_sentence_window_retrieval(
            search_result=search_result,
            k=k,
            client=client
        )
        return search_result_window
    return search_result