"""
Vector DB Builder for Weaviate
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

import weaviate
import weaviate.classes as wvc
from weaviate.classes.config import Property, DataType, Configure, VectorDistances, ReferenceProperty
from weaviate.util import generate_uuid5  # Generate a deterministic 
from weaviate.classes.init import Auth
from weaviate.classes.data import DataReference

try:
    from  ..agent.vector_db_utils import VectorDB_Schema
    from ..ingestion.chunker import DocumentChunk
except:
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.vector_db_utils import VectorDB_Schema
    from ingestion.chunker import DocumentChunk

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class VectorDB_Data:
    """ Class to handle Weaviate vector database operations """

    def __init__(self, 
            collection_chunk: str = "Chunks", 
            collection_fulldoc: str = "FullDoc",
            basis: str = "local"):
        self.basis = basis
        self._initialized = False
        self.collection_chunk = collection_chunk
        self.collection_fulldoc = collection_fulldoc
        self.vector_client = VectorDB_Schema(class_chunk = collection_chunk, class_fulldoc= collection_fulldoc)
        


    def initialize_database(self):
        """ Initialize the Weaviate client """
        if not self._initialized:
            self.vector_client.initialize_database(basis=self.basis)
            self._initialized = True

    def close_database(self):
        """ Close the Weaviate client connection """
        if self._initialized:
            self.vector_client.close_database()
            self._initialized = False

    def add_data(self, full_doc_list: list[Dict[str, Any]], embedded_chunks_list: list[DocumentChunk]):
        """ Add data to the database """
        if not self._initialized:
            self.initialize_database()
        logger.info("Starting data ingestion into vector database...")
        result_doc = self._add_full_document(full_doc_list)
        result_chunks = self._add_chunks(embedded_chunks_list)
        result_all = {**result_doc, **result_chunks}
        return result_all

    def _add_full_document(self, full_doc_list: list[Dict[str, Any]]):
        """ Add full documents to the database """
        full_doc_list_db = list()

        if not full_doc_list:
            logger.warning("No full documents to add.")
            return

        logger.info(f"Full Doc ingestion started for {len(full_doc_list)} documents.")

        for i, d in enumerate(full_doc_list):
            full_doc_list_db.append(wvc.data.DataObject(
                properties={
                    "title": d["title"],
                    "source": d["file_path"],
                    "md": d["full_markdown"],
                    "client": d["client"]
                    },
                uuid= generate_uuid5(d)  
            ))
        

        full_doc_collection = self.vector_client.client.collections.use(self.collection_fulldoc)
        response = full_doc_collection.data.insert_many(full_doc_list_db)

        logger.info(f"Full Doc ingestion complete: {len(response.uuids)}/{len(full_doc_list)} documents created")

        result = {
            "created_docs": len(response.uuids),
            "total_docs": len(full_doc_list),
            "errors_doc": len(response.errors)
        }
        return result

    def _add_chunks(self, embedded_chunks_list: List[DocumentChunk]):
        """ Add document chunks to the database with references to full documents """
        chunks_collection = self.vector_client.client.collections.use(self.collection_chunk)
        fulldoc_collection = self.vector_client.client.collections.use(self.collection_fulldoc)
        batch_size = 50 
        total_batches = (len(embedded_chunks_list) + batch_size - 1) // batch_size

        from weaviate.classes.config import ReferenceProperty

        schema_chunks = chunks_collection.config.get()
        if not any(ref.name == "document" for ref in schema_chunks.references):
            chunks_collection.config.add_reference(
                ReferenceProperty(
                    name="document", 
                    target_collection=self.collection_fulldoc
                )
            )

        # Build a quick lookup for FullDoc UUIDs by source to avoid iterating the collection
        # for every single chunk.
        source_to_doc_uuid: Dict[str, Any] = {}
        for item in fulldoc_collection.iterator():
            source = item.properties.get("source")
            if source:
                source_to_doc_uuid[source] = item.uuid
        

        logger.info(f"Starting chunk ingestion into vector database in batches (batch size: {batch_size})...")
        with chunks_collection.batch.fixed_size(batch_size=batch_size) as batch:
            for i, chunk in enumerate(embedded_chunks_list):
                chunk_uuid = generate_uuid5(chunk)  

                source = chunk.metadata.get("source")
                doc_uuid = source_to_doc_uuid.get(source)
                if not doc_uuid:
                    logger.error(f"No FullDoc found for chunk source={source!r}; skipping chunk index={getattr(chunk, 'index', None)}")
                    continue

                
                
                current_batch = (i // batch_size) + 1
                if i % batch_size == 0:
                    logger.info(f"Processing batch {current_batch}/{total_batches}")

                batch.add_object(
                    properties={
                        "client": chunk.metadata.get("client"),
                        "title": chunk.metadata.get("title"),
                        "source": chunk.metadata.get("source"),
                        "page": chunk.metadata.get("page"),
                        "type": chunk.metadata.get("type"),
                        "heading_lvl1": chunk.metadata.get("heading_lvl1"),
                        "heading_lvl2": chunk.metadata.get("heading_lvl2"),
                        "heading_lvl3": chunk.metadata.get("heading_lvl3"),
                        "content": chunk.content,
                        "md": chunk.md,
                        "index": chunk.index,
                    },
                
                    uuid=chunk_uuid,
                    vector=chunk.embedding
                )
                batch.add_reference(
                    from_property = "document",
                    from_uuid = chunk_uuid,
                    to = doc_uuid
                )
                if batch.number_errors > 10:
                    logger.error("Batch import stopped due to excessive errors.")
                    break


        failed_objects = chunks_collection.batch.failed_objects

        if failed_objects:
            print(f"Number of failed imports: {len(failed_objects)}")
            for failed in failed_objects[:3]:  # Show first 3 failures
                print(f"Failed: {failed}")

        failed_references = chunks_collection.batch.failed_references
        if failed_references:
            logger.error(f"Number of failed imports: {len(failed_references)}")
            for failed in failed_references[:3]:  # Show first 3 failures
                print(f"Failed: {failed}")

        # NOTE: We intentionally do not add reverse FullDoc -> Chunks references here.
        # Chunk -> FullDoc references already exist via the "document" reference.
        # Adding the reverse references requires a large `reference_add_many` call which can
        # easily time out for bigger ingestions.

        created_chunks = len(embedded_chunks_list) - len(failed_objects)

        result = {
            "created_chunks": created_chunks,
            "total_chunks": len(embedded_chunks_list),
            "errors_chunks": len(failed_objects),
            "errors_references": len(failed_references)
        }

        logger.info(f"Added Chunks and Full Doc references to vector database.")

        return result

    def clear_database(self):
        """ Clear existing collections in the database """
        if not self._initialized:
            self.initialize_database()
        try:
            self.vector_client.clean_collections()
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
            raise
                            

def create_vector_db(
    collection_chunk: str = "Chunks", 
    collection_fulldoc: str = "FullDoc",
    basis: str = "local"
    ) -> VectorDB_Data:
        """
        Create Weaviate vector database handler

        Args:
            collection_chunk: Name of the chunk collection
            collection_fulldoc: Name of the full document collection

        Returns:
            VectorDB_Data instance
        """
        vector_db = VectorDB_Data(
            collection_chunk=collection_chunk,
            collection_fulldoc=collection_fulldoc,
            basis=basis
            )
        return vector_db

                        