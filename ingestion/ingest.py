"""
Main ingestion script for processing markdown documents into vector DB and knowledge graph.
"""

import os
import asyncio
import logging
import json
import glob
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import argparse

import asyncpg
from dotenv import load_dotenv



from .data_prep import MarkdownPrep, ItemPrep, TablePrep
from .chunker import ChunkingConfig, create_chunker
from .embedder import create_embedder
from .graph_builder import create_graph_builder
from .vector_db_builder import create_vector_db

# Import agent utilities
try:
    from ..agent.graph_utils import initialize_graph, close_graph
    from ..agent.models import IngestionConfig, IngestionResult
except ImportError:
    # For direct execution or testing
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from agent.graph_utils import initialize_graph, close_graph
    from agent.models import IngestionConfig, IngestionResult


# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Suppress verbose logs from httpx
logging.getLogger("httpx").setLevel(logging.WARNING)


class DocumentIngestionPipeline:
    """Pipeline for ingesting documents into a vector DB and knowledge graph."""

    def __init__(
            self,
            config: IngestionConfig,
            documents_folder: str = "json_to_ingest",
            clean_before_ingest: bool = False,
            client: str = "default_client_2",
            vector_db_only: bool = False
    ):
        self.config = config
        self.documents_folder = documents_folder
        self.clean_before_ingest = clean_before_ingest
        self.client = client
        self.vector_db_only = vector_db_only


        # initialize components
        self.chunker_config = ChunkingConfig(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            max_chunk_size=config.max_chunk_size,
            chunk_separator=config.chunk_separator,
            chunking_method=config.chunking_method
        )

        self.chunker = create_chunker(self.chunker_config)
        self.embedder = create_embedder()
        if self.vector_db_only == False:
            self.graph_builder = create_graph_builder()
        self.vector_db_builder = create_vector_db(basis="local")
        self._initizalized = False
    
    async def initialize(self):
        """ Initialize the ingestion pipeline components """
        if self._initizalized:
            return
        
        logger.info("Initializing Ingestion Pipeline components...")


        # Initialize database connections

        # evtl goblal initialization of vector db
        self.vector_db_builder.initialize_database()
        if self.vector_db_only == False:
            await initialize_graph()
            await self.graph_builder.initialize()
        self._initizalized = True
        logger.info("Ingestion Pipeline components initialized successfully.")

    async def close(self):
        """ Close the ingestion pipeline components """
        if self._initizalized:

            await self.graph_builder.close()
            self.vector_db_builder.close_database()
            if self.vector_db_only == False:
                await close_graph()

            self._initizalized = False
            logger.info("Ingestion Pipeline components closed.")

    async def ingest_documents_pipeline(
        self,
        progress_callback: Optional[callable] = None,
        
    ) -> List[IngestionResult]:
        """
        Ingest documents from the specified folder into the vector DB and knowledge graph.

        Args:
            progress_callback: Optional callback function to report progress.
        Returns:
            List of IngestionResult objects summarizing the ingestion process.
        """

        if not self._initizalized:
            await self.initialize()


        # Clean existing data if required
        if self.clean_before_ingest:
            logger.info("Cleaning existing data from vector DB and knowledge graph...")
            await self.graph_builder.clear_graph()
            self.vector_db_builder.clear_database()

            logger.info("Existing data cleaned.")



        # Load json documents
        json_objs = self._read_json_files()

        if not json_objs: 
            logger.warning("No files found for ingestion.")
            return []

        logger.info(f"Found {len(json_objs)} files for ingestion.")

        results = await self._ingest_documents(json_objs)

        logger.info("Document ingestion completed.")

        return results
    

    def _get_data_files_json(self) -> list[str]:
        """ Retrieve all JSON files from the specified directory """
        if not os.path.exists(self.documents_folder):
            logging.error(f"Directory does not exist: {self.documents_folder}")
            return []
        
        files_json = []
        for f in os.listdir(self.documents_folder):
            fname = os.path.join(self.documents_folder, f)
            if os.path.isfile(fname):
                files_json.append(fname)

        if not files_json:
            logging.info(f"No files found in directory: {self.documents_folder}")
        return files_json


    def _read_json_files(self) -> list[Dict[str, Any]]:
        json_objs = []
        file_paths = self._get_data_files_json()
        for file_path in file_paths:
            with open(file_path, 'r') as f:
                data = json.load(f)
                data["file_path"] = file_path
            #  json_objs.append(data["pages"])
                json_objs.append(data)
        return json_objs

    async def _ingest_documents(self, json_objs: list[Dict[str, Any]]) -> List[IngestionResult]:
        """
        Ingest documents from JSON objects into vector DB and knowledge graph.

        Args:
            json_objs: List of JSON objects representing documents.
        Returns:
            List of IngestionResult objects summarizing the ingestion process.
        """ 
        start_time = datetime.now()

        # Data Prep
        ## Markdown preprocessing

        ### data cleaning
        prep = MarkdownPrep(client=self.client)
        md_json_prep = prep.markdown_prep(json_objs)
        md_json_full = prep.markdown_full_doc(json_objs)
        doc_titles = prep.title_list(json_objs)

        ### create items
        md_items =  ItemPrep().create_items(md_json_prep)

        ## Create table summaries
        md_json_final = await TablePrep().create_table_summaries(md_items)

        # Vector DB ingestion

        ## Chunking
        chunks = await self.chunker.chunk_documents(content=md_json_final)

        if not chunks:
            logger.warning("No chunks created from documents.")
            # return ingestion results
        
        logger.info(f"Created {len(chunks)} chunks.")

        ## Embedding

        embedded_chunks = await self.embedder.embed_chunks(chunks)
        logger.info(f"Embedded {len(embedded_chunks)} chunks.")

        ## Vector DB insertion
        result_vector_db = self.vector_db_builder.add_data( full_doc_list = md_json_full, embedded_chunks_list = embedded_chunks)

        logger.info("Documents added to vector database.")

        if self.vector_db_only == False:
            # Knowledge Graph ingestion
            try: 
                logger.info("Starting knowledge graph ingestion (this may take a while)...")

                # Ingest data into the knowledge graph
                result_graph = await self.graph_builder.add_items_to_graph(md_json_final, group_id=self.client)

                logger.info("Knowledge graph ingestion completed successfully.")

            except Exception as e:
                logger.error(f"Error during knowledge graph ingestion: {e}")

        processing_time = (datetime.now() - start_time).total_seconds() * 1000  

        return IngestionResult(
            created_docs = doc_titles,
            total_chunks = len(chunks),
            total_episodes = result_graph.get("episodes_created", 0) if self.vector_db_only == False else 0,
            processing_time_ms = processing_time,
            errors_graph = result_graph.get("errors", []) if self.vector_db_only == False else [],
            errors_vector_db = result_vector_db.get("errors_chunks", [])
        )


async def main():
    """Main function for running ingestion."""
    parser = argparse.ArgumentParser(description="Ingest documents into vector DB and knowledge graph")
    parser.add_argument("--documents", "-d", default="ingestion/json_to_ingest", help="Documents folder path")
    parser.add_argument("--clean", "-c", action="store_true", help="Clean existing data before ingestion")
    parser.add_argument("--chunk-size", type=int, default=400, help="Chunk size for splitting documents")
    parser.add_argument("--chunk-overlap", type=int, default=0, help="Chunk overlap size")
    parser.add_argument("--client", type=str, default="Walmart", help="Credit Single Risk Client")
    parser.add_argument("--separators-chunking", type=List[str], default=["\n\n", "\n", ". ", "?", "!", " ", ""], help="Chunking separators")
    #parser.add_argument("--no-recursive", action="store_true", help="Disable recursive chunking")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--vector_db_only", "-vdb", action="store_true", help="Only ingest into vector database, skip knowledge graph")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Create ingestion configuration
    config = IngestionConfig(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        #chunking_method=not args.no_recursive,
        chunk_separator=args.separators_chunking
    )
    
    # Create and run pipeline
    pipeline = DocumentIngestionPipeline(
        config=config,
        documents_folder=args.documents,
        clean_before_ingest=args.clean,
        client=args.client,
        vector_db_only=args.vector_db_only
    )
    
    def progress_callback(current: int, total: int):
        print(f"Progress: {current}/{total} documents processed")
    
    try:
        start_time = datetime.now()
        
        results = await pipeline.ingest_documents_pipeline(progress_callback)
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        # Print summary
        print("\n" + "="*50)
        print("INGESTION SUMMARY")
        print("="*50)
        print(f"Documents processed: {len(results.created_docs)}")
        print(f"Total chunks created: {results.total_chunks}")
        print(f"Total graph episodes: {results.total_episodes}")
        print(f"Total errors: {results.errors_vector_db + len(results.errors_graph)}")
        print(f"Total processing time: {total_time:.2f} seconds")
        print()
        

        
    except KeyboardInterrupt:
        print("\nIngestion interrupted by user")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        await pipeline.close()



if __name__ == "__main__":
    asyncio.run(main())
