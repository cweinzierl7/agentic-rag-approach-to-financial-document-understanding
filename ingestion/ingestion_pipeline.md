# Complete Data Ingestion Pipeline: Weaviate + Graphiti

## Executive Summary

This document describes the complete data ingestion pipeline that transforms financial PDF documents into a dual-indexed knowledge system combining vector search (Weaviate) and knowledge graph (Graphiti/Neo4j) capabilities. This hybrid approach enables both semantic similarity retrieval and structured entity-relationship queries for the multi-agent credit risk reporting system.

**Purpose**: Create a comprehensive, queryable knowledge base from financial documents that supports:
- Hybrid search  (Weaviate)
- Graph search (entities and facts) (Graphiti/Neo4j)


**Key Capabilities**:
- Processes multi-format financial documents (PDFs with text, tables, complex layouts)
- Dual indexing: Vector embeddings for semantic search + Knowledge graph for structured queries
- Automatic entity and relationship extraction using LLM-based analysis (Graphiti)
- Episode-based graph construction preserving temporal and document context
- Multi-tenant support with client isolation across both systems

**Technical Stack**:
- **PDF Parsing**: Marker library
- **Data Prep**: Custom markdown cleaning and item structuring
- **Chunking**: LangChain recursive text splitter
- **Embeddings**: OpenAI text-embedding-3-small (1536d)
- **Vector DB**: Weaviate (semantic + BM25 search)
- **Knowledge Graph**: Graphiti on Neo4j (entity extraction, relationship mapping)

**Output**: A dual-indexed knowledge system where:
- **Weaviate** provides fast semantic retrieval of relevant document chunks
- **Graphiti/Neo4j** provides structured entity-relationship queries
- **Multi-agent system** leverages both for comprehensive information retrieval

---

## Architecture Overview

### Complete Pipeline Flow

```
                          PDF Documents
                               │
                               ▼
                    ┌──────────────────┐
                    │  PDF Parsing     │ → Marker
                    │  (Marker)        │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Markdown Prep   │ → Clean formatting
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Item Creation   │ → Structure metadata
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │  Table Summary   │ → LLM summaries
                    └────────┬─────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │  WEAVIATE PIPELINE  │   │  GRAPHITI PIPELINE  │
    └─────────────────────┘   └─────────────────────┘
                 │                       │
                 ▼                       ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │  Chunking (400 tok) │   │  Episode Creation   │
    └──────────┬──────────┘   └──────────┬──────────┘
               │                          │
               ▼                          ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │  Embedding Gen.     │   │  Entity Extraction  │
    │  (1536-dim)         │   │  (LLM-based)        │
    └──────────┬──────────┘   └──────────┬──────────┘
               │                          │
               ▼                          ▼
    ┌─────────────────────┐   ┌─────────────────────┐
    │  Weaviate Storage   │   │  Neo4j Graph Store  │
    │  • FullDoc          │   │  • EntityNodes      │
    │  • Chunks           │   │  • EpisodeNodes     │
    │                     │   │  • EntityEdges      │
    └─────────────────────┘   └─────────────────────┘
                 │                       │
                 └───────────┬───────────┘
                             │
                             ▼
                  ┌─────────────────────┐
                  │   Dual-Indexed      │
                  │  Knowledge System   │
                  └─────────────────────┘
```

### System Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **PDF Parser** | Marker | Extract text, tables, metadata from PDFs |
| **Data Preprocessor** | Custom Python | Clean markdown, structure items with metadata |
| **Table Summarizer** | GPT-4.1 | Generate natural language summaries of tables |
| **Chunker** | LangChain | Split documents into 200-token chunks |
| **Embedder** | OpenAI API | Generate 1536-dim vectors for semantic search |
| **Vector DB** | Weaviate | Store and search embedded chunks (hybrid search) |
| **Graph Builder** | Graphiti | Extract entities and relationships |
| **Knowledge Graph** | Neo4j | Store entity-relationship graph |
| **Orchestrator** | DocumentIngestionPipeline | Coordinate all components |

---

## Part 1: Weaviate Vector Database Pipeline

### Purpose

Create searchable, embedded document chunks for semantic and keyword retrieval.

### Process Details

#### 1. Document Preprocessing
- **Input**: JSON files from `json_to_ingest/` (Marker output)
- **Markdown Prep**: Removes formatting artifacts, normalizes whitespace
- **Item Creation**: Structures content into `Item` objects with:
  - Document title, source path, page number
  - Item type (text, table, heading)
  - Hierarchical heading levels (lvl1-3)
  - Client identifier

#### 2. Table Summarization
- **Challenge**: Tables are difficult to embed meaningfully
- **Solution**: GPT-4.1 generates natural language summaries
- **Result**: Each table gets both original markdown and searchable summary

#### 3. Chunking
- **Method**: Recursive character text splitter (LangChain)
- **Configuration**:
  - Target: 400 tokens per chunk
  - Overlap: 0-50 tokens (configurable)
  - Separators: `["\n\n", "\n", ". ", "?", "!", " ", ""]`
- **Special handling**: Tables remain as single chunks (not split)

#### 4. Embedding Generation
- **Model**: OpenAI text-embedding-3-small
- **Dimensions**: 1536
- **Batching**: 100 chunks per request
- **Features**:
  - Automatic retry with exponential backoff
  - Rate limit handling
  - Content truncation for oversized chunks (~8191 tokens max)

#### 5. Weaviate Storage

**Schema Design**:

Two collections with unidirectional references:

| Collection | Properties | Indexed | Purpose |
|------------|-----------|---------|---------|
| **FullDoc** | `title`, `source`, `md`, `client` | No vectors | Complete document storage |
| **Chunks** | `client`, `title`, `source`, `page`, `type`, `heading_lvl1-3`, `content`, `md`, `index` | 1536-dim vector | Searchable segments |

**References**: Each `Chunk` → `FullDoc` (one-to-many, unidirectional)

**Insertion Process**:
1. Insert all FullDoc entries with deterministic UUIDs
2. Batch insert Chunks (batch size: 50) with:
   - Text content and metadata
   - Vector embeddings
   - References to parent FullDoc
3. Log failures, continue on errors

**Benefits**:
- Deterministic UUIDs enable idempotent re-ingestion
- Batch processing prevents timeouts
- Metadata filtering during retrieval
- Hybrid search (semantic + BM25 keyword)

---

## Part 2: Graphiti Knowledge Graph Pipeline

### Purpose

Extract and structure entities, relationships, and facts from documents into a queryable knowledge graph.

### Graphiti Framework

Graphiti is a Python library that automatically constructs knowledge graphs from text using LLM-based extraction. It:
- Extracts entities (companies, KPIs, people, dates)
- Identifies relationships between entities
- Creates "episode" nodes representing document segments
- Links episodes to extracted entities
- Maintains temporal context

### Process Details

#### 1. Episode Creation

**What is an Episode?**
An episode represents a discrete unit of information from the source documents. In this pipeline, each `Item` (from the preprocessing stage) becomes one episode.

**Episode Structure**:
```python
{
    "name": "Document_Title_ItemIndex_Timestamp",
    "episode_body": "Document content (max 10,000 chars)",
    "source": "text",  # Always text type
    "source_description": "Document: [title], Page: [n]",
    "reference_time": "2024-01-15T10:30:00Z",
    "group_id": "client_name",  # For multi-tenant isolation
    "metadata": {
        "document_title": "...",
        "page": 42,
        "type": "table",
        "index": 123,
        "document_source": "/path/to/file.pdf"
    }
}
```

**Content Preparation**:
- Maximum 10,000 characters per episode
- Truncation at sentence boundaries when needed
- Document title prepended for context

#### 2. Entity & Relationship Extraction (LLM-Powered)

When an episode is added to Graphiti:

1. **Entity Extraction**: LLM (GPT-4.1) analyzes content and identifies:
   - Companies (e.g., "RWE AG", "Northwind Industries")
   - Financial metrics (e.g., "EBITDA", "Revenue")
   - Dates and fiscal periods
   - Industry sectors
   - Rating agencies

2. **Relationship Mapping**: LLM identifies connections:
   - "RWE AG" → `HAS_KPI` → "EBITDA"
   - "RWE AG" → `OPERATES_IN` → "Energy Sector"
   - "Moody's" → `RATED` → "RWE AG"

3. **Fact Linking**: Episodes are linked to extracted entities:
   - Episode → `MENTIONS` → Entity
   - Episode → `CONTAINS_FACT` → Entity relationship

#### 3. Graph Schema (Neo4j)

**Node Types**:
- **EntityNode**: Represents entities (companies, KPIs, people, etc.)
  - Properties: `name`, `summary`, `uuid`, `created_at`
- **EpisodeNode**: Represents document segments
  - Properties: `name`, `content`, `source_description`, `reference_time`, `group_id`, `metadata`

**Edge Types**:
- **EntityEdge**: Relationships between entities
  - Properties: `fact`, `episodes` (list of episode UUIDs supporting this fact)
- **EpisodeEdge**: Links episodes to entities they mention

**Indexing**:
- Entity names (full-text search)
- Entity embeddings (1536-dim vectors for semantic search)
- Episode timestamps (temporal queries)
- Group IDs (multi-tenant filtering)

#### 4. Incremental Graph Building

Graphiti builds the graph incrementally:
- New episodes are processed one at a time
- LLM extracts entities and relationships
- Deduplication: If entity already exists, it's updated/merged
- Fact consolidation: Multiple episodes can support the same relationship
- **Small delay (0.5s)** between episodes to avoid overwhelming LLM API

#### 5. Multi-Tenant Isolation

Each episode tagged with `group_id` (client identifier):
- Search queries filter by `group_id`
- Prevents cross-client information leakage
- Enables per-client graph analytics

---

## Implementation Details

### Code Organization

```
ingestion/
├── ingest.py                    # Main pipeline orchestrator
├── pdf_parse.py                 # Marker PDF extraction
├── data_prep.py                 # Markdown preprocessing
├── chunker.py                   # Text chunking
├── embedder.py                  # Embedding generation
├── vector_db_builder.py         # Weaviate operations
└── graph_builder.py             # Graphiti operations

agent/
├── vector_db_utils.py           # Weaviate wrapper
└── graph_utils.py               # GraphitiClient wrapper
```

### Key Classes

**DocumentIngestionPipeline** (`ingest.py`)
- Orchestrates entire dual-ingestion process
- Manages initialization and cleanup for both systems
- Handles batch processing and error recovery

**VectorDB_Data** (`vector_db_builder.py`)
- Weaviate client management
- Batch insertion with deterministic UUIDs
- Collection and reference creation

**GraphBuilder** (`graph_builder.py`)
- Wraps GraphitiClient for ingestion
- Episode creation and content preparation
- Batch processing with rate limiting

**GraphitiClient** (`graph_utils.py`)
- Neo4j connection management
- LLM and embedder configuration
- Search and retrieval methods

**VectorDB_Schema** (`vector_db_utils.py`)
- Weaviate schema and collection management
- Hybrid search (BM25 + vector) with client filtering
- Sentence window retrieval for expanded context

### Configuration

#### 1. PDF Parsing (LlamaParse)

```python
from ingestion.pdf_parse import pdf_parser

parser = pdf_parser(
    data_dir="./pdf_to_ingest"   # Directory containing PDFs to parse
)
parser.parse_pdfs()              # Outputs JSON to json_to_ingest/
```

**Command-Line Usage:**

```bash
python -m ingestion.pdf_parse
```

- Expects PDFs in `./pdf_to_ingest` folder
- Outputs parsed JSON files to `json_to_ingest/`

**LlamaParse Settings** (configured in `pdf_parser`):
- `parse_mode`: "parse_page_with_agent" (AI-assisted parsing)
- `num_workers`: 4 (parallel processing)
- `extract_layout`: True (preserve document structure)
- `result_type`: "markdown" (output format)
- `adaptive_long_table`: True (handle multi-page tables)

#### 2. Document Ingestion Pipeline

```python
from ingestion.ingest import DocumentIngestionPipeline
from agent.models import IngestionConfig

config = IngestionConfig(
    chunk_size=400,              # Target tokens per chunk
    chunk_overlap=0,             # Overlap between chunks
    max_chunk_size=400,          # Maximum chunk size
    chunking_method="recursive"  # LangChain splitter method
)

pipeline = DocumentIngestionPipeline(
    config=config,
    documents_folder="json_to_ingest",  # Input folder with parsed JSONs
    clean_before_ingest=False,          # Clear existing data before ingestion?
    client="company_name",              # Multi-tenant client identifier
    vector_db_only=False                # True = skip Graphiti, only Weaviate
)

# Run dual ingestion
await pipeline.initialize()
results = await pipeline.ingest_documents_pipeline()
await pipeline.close()
```

#### 3. Command-Line Usage

Run ingestion directly from terminal:

```bash
python -m ingestion.ingest [OPTIONS]
```

**Available Arguments:**

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--documents` | `-d` | `ingestion/json_to_ingest` | Path to folder with parsed JSON files |
| `--clean` | `-c` | `False` | Clear existing data before ingestion |
| `--chunk-size` | | `400` | Target chunk size in tokens |
| `--chunk-overlap` | | `0` | Overlap between consecutive chunks |
| `--client` | | `Walmart` | Multi-tenant client identifier |
| `--separators-chunking` | | `["\n\n", "\n", ". ", ...]` | Chunking separators |
| `--verbose` | `-v` | `False` | Enable debug logging |
| `--vector_db_only` | `-vdb` | `False` | Skip Graphiti, only ingest to Weaviate |

**Examples:**

```bash
# Basic ingestion with defaults
python -m ingestion.ingest

# Ingest with custom client and clean existing data
python -m ingestion.ingest -d ./my_docs -c --client "RWE"

# Vector DB only (faster, no graph)
python -m ingestion.ingest --vector_db_only -v

# Custom chunking settings
python -m ingestion.ingest --chunk-size 300 --chunk-overlap 50
```

### Environment Variables

```bash
# Neo4j (for Graphiti)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Weaviate
WEAVIATE_URL=http://localhost:8080
WEAVIATE_API_KEY=your_key  # If using cloud

# LLM (for Graphiti entity extraction)
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=your_openai_key
LLM_CHOICE_KG=gpt-4.1

# Embeddings (for both systems)
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your_openai_key
EMBEDDING_MODEL=text-embedding-3-small
VECTOR_DIMENSION=1536
```

---

## Maintenance Operations

### Clearing Data

```python
# Clear both systems
pipeline = DocumentIngestionPipeline(
    config=config,
    clean_before_ingest=True  # ← Clears existing data
)
await pipeline.initialize()
# Both Weaviate and Graphiti cleared
```

---

## Summary

The complete ingestion pipeline creates a powerful dual-indexed knowledge system:

1. **Weaviate Vector Database** provides fast, semantic retrieval of document chunks with hybrid search capabilities
2. **Graphiti Knowledge Graph** provides structured entity-relationship queries with temporal context
3. **Together**, they enable the multi-agent system to answer complex financial queries by combining:
   - Semantic similarity (find relevant passages)
   - Structured relationships (find connected entities)
   - Metadata filtering (narrow by client, year, document type)
   - Hybrid strategies (use best tool for each query type)

The pipeline processes a 200-page financial report in ~4 minutes, creating ~400 searchable chunks in Weaviate and ~200 interconnected episodes in Graphiti, all while maintaining multi-tenant isolation and comprehensive error handling.
