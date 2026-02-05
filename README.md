# Agentic RAG for Financial Document Understanding

An agentic rag approach for automated credit risk reporting that combines traditional RAG (vector search) with knowledge graph capabilities to analyze financial documents and extract Key Performance Indicators (KPIs).

Built with:

- **OpenAI Agents SDK** for the AI Agent Framework
- **Graphiti** for the Knowledge Graph (entity/fact extraction)
- **Weaviate** for the Vector Database (semantic + BM25 search)
- **Neo4j** for the Knowledge Graph Engine
- **LlamaParse** for PDF parsing

## Overview

This system implements two agent architectures for credit risk KPI retrieval:

1. **Single-Agent Architecture**: A monolithic agent handling all retrieval tasks
2. **Multi-Agent Architecture**: Specialized agents (Router, Quantitative Retriever, Qualitative Retriever, Derived-KPI Retriever, Writer) coordinated by a Python orchestrator

Both architectures query a dual-indexed knowledge system:
- **Weaviate**: Chunked financial documents with hybrid search (semantic + keyword)
- **Graphiti/Neo4j**: Structured entity-relationship graph with temporal context

## Prerequisites

- Python 3.11 or higher
- Neo4j database (for knowledge graph via Graphiti)
- Weaviate instance (for vector database)
- OpenAI API key (for embeddings and LLM)
- LlamaParse API key (for PDF parsing)

## Installation

### 1. Set up a virtual environment

```bash
# Create and activate virtual environment
python -m venv        # python3 on Linux
source venv/bin/activate  # On Linux/macOS
# or
venv\Scripts\activate     # On Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up Neo4j

You have a couple options for setting up Neo4j:

#### Option A: Using Neo4j Aura (Cloud)
1. Create a free account at [Neo4j Aura](https://neo4j.com/cloud/aura/)
2. Create a new database instance
3. Note your connection URI, username, and password

#### Option B: Using Neo4j Desktop (Local)
1. Download and install [Neo4j Desktop](https://neo4j.com/download/)
2. Create a new project and add a local DBMS
3. Start the DBMS and set a password
4. Note the connection details (URI, username, password)

### 4. Set up Weaviate

You can use Weaviate Cloud or run it locally:


#### Option A: Local Docker
```bash
docker run -d -p 8080:8080 semitechnologies/weaviate:latest
```

#### Option B: Weaviate Cloud 
1. Create an account at [Weaviate Cloud](https://console.weaviate.cloud/)
2. Create a new cluster
3. Note your cluster URL and API key
- If using **Weaviate Cloud** instead of a local instance, update `ingestion/ingest.py`:
  - Change `create_vector_db(basis="local")` to `create_vector_db(basis="cloud")`
  - The default is set to `"local"`


### 5. Configure environment variables

Copy `env.example` to `.env` and configure the values:

```bash
# PDF Parsing (LlamaParse)
PDF_PARSE_API_KEY=your_llamaparse_api_key

# Weaviate Vector Database
WEAVIATE_URL=https://your-cluster.weaviate.network
WEAVIATE_API=your_weaviate_api_key

# Neo4j Knowledge Graph
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# LLM Configuration
LLM_PROVIDER=openai
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-api-key
LLM_CHOICE=your_llm_choice

# Embedding Configuration
EMBEDDING_PROVIDER=openai
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-your-api-key
EMBEDDING_MODEL=your_embedding_choice
```

## Quick Start

### 1. Prepare Your PDF Documents

Add your financial PDF documents (annual reports, financial statements, etc.) to the `ingestion/pdf_to_ingest/` folder:

```bash
# Add PDF files to parse
cp your_annual_report.pdf ingestion/pdf_to_ingest/
```

### 2. Parse PDFs with LlamaParse

First, convert PDFs to JSON format:

```bash
python -m ingestion.pdf_parse
```

This uses LlamaParse to extract structured content from PDFs and saves JSON files to `ingestion/json_to_ingest/`.

### 3. Run Document Ingestion

Ingest the parsed documents into the vector database and knowledge graph:

```bash
# Basic ingestion
python -m ingestion.ingest --client "YourCompany" 

# Clean existing data and re-ingest
python -m ingestion.ingest --clean --client "YourCompany" 

# Ingest only to vector database (skip knowledge graph)
python -m ingestion.ingest --vector_db_only --client "YourCompany" 

# Custom chunking settings
python -m ingestion.ingest --chunk-size 600 --chunk-overlap 50 --client "YourCompany" 

# Full example with all options
python -m ingestion.ingest -d ingestion/json_to_ingest -c --chunk-size 400 -v --client "YourCompany" 
```

#### Ingestion CLI Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--documents` | `-d` | `ingestion/json_to_ingest` | Documents folder path |
| `--clean` | `-c` | `false` | Clean existing data before ingestion |
| `--chunk-size` | | `400` | Chunk size for splitting documents |
| `--chunk-overlap` | | `0` | Chunk overlap size |
| `--client` | | `default_client` | Credit risk client name |
| `--verbose` | `-v` | `false` | Enable verbose logging |
| `--vector_db_only` | `-vdb` | `false` | Only ingest to vector DB, skip knowledge graph |

The ingestion process will:
- Parse and chunk your documents using LangChain's recursive text splitter
- Generate embeddings using OpenAI's text-embedding-3-small (1536 dimensions)
- Store chunks in Weaviate with hybrid search capabilities
- Extract entities and relationships for the Graphiti knowledge graph

**Note**: Knowledge graph extraction is computationally intensive and may take significant time for large document sets.

### 4. Run the Single Agent

```bash
python -m agent.single_agent.single_agent
```

**Note**: Before running, configure the client name and retrieval parameters in `agent/single_agent/single_agent.py`.

### 5. Run the Multi-Agent System

```bash
python -m agent.multi_agent.orchestrator
```

**Note**: Before running, configure the client name and retrieval parameters in `agent/multi_agent/orchestrator.py`.

## How It Works

### The Power of Hybrid RAG + Knowledge Graph

This system combines the best of both worlds:

**Weaviate Vector Database**:
- Hybrid search combining semantic similarity (dense vectors) + BM25 keyword matching (sparse vectors)
- Fast retrieval of contextually relevant document chunks
- Sentence window retrieval for expanded context

**Knowledge Graph (Neo4j + Graphiti)**:
- Temporal entity-relationship extraction from financial documents
- Graph traversal for discovering connections between KPIs, companies, and events
- Structured fact storage with source attribution

**Intelligent Agent System**:
- **Single Agent**: Monolithic approach with direct tool access
- **Multi-Agent**: Specialized agents coordinated by an orchestrator:
  - **Router Agent**: Classifies queries and routes to appropriate retrievers
  - **Quantitative Retriever**: Handles numerical KPIs 
  - **Qualitative Retriever**: Handles qualitative KPIs 
  - **Derived-KPI Agent**: Calculates complex metrics from retrieved data
  - **Writer Agent**: Synthesizes final responses with citations

### Available Tools

The agents have access to these search tools:

| Tool | Description |
|------|-------------|
| `vector_hybrid_search` | Hybrid search (semantic + BM25) in Weaviate |
| `graph_search_facts` | Search for facts/relationships in Graphiti |
| `graph_search_entities` | Search for entities in the knowledge graph |
| `calculator` | Performs arithmetic calculations for derived KPIs |



## Key Features

- **Dual Architecture**: Single-agent and multi-agent approaches for comparison
- **Hybrid Search**: Combines semantic vector search with BM25 keyword matching
- **Knowledge Graph Integration**: Graphiti for temporal entity-relationship extraction
- **PDF Processing**: LlamaParse for accurate financial document parsing
- **Credit Risk Focus**: Optimized for KPI extraction and financial analysis
- **Evaluation Framework**: RAGAS and custom metrics for answer quality assessment

## Project Structure

```
agentic-rag-approach-to-financial-document-understanding/
├── agent/                          # AI agent implementations
│   ├── single_agent/               # Single-agent architecture
│   │   ├── single_agent.py         # Main agent with OpenAI Agents SDK
│   │   ├── prompt_single_agent.py  # System prompts
│   │   └── outputs_single_agent/   # Single-agent output reports
│   ├── multi_agent/                # Multi-agent architecture
│   │   ├── orchestrator.py         # Python orchestrator
│   │   ├── router_agent.py         # Query classification
│   │   ├── retrieval_agent_quantitative.py   # Quantitative retrieval agent
│   │   ├── retrieval_agent_qualitative.py    # Qualtiative retrieval agent
│   │   ├── derived_kpi_agent.py    # KPI calculations
│   │   ├── writer_agent.py         # Response synthesis
│   │   └── outputs_multi_agent/    # Multi-agent output reports
│   ├── tools.py                    # Search tool definitions
│   ├── vector_db_utils.py          # Weaviate utilities
│   ├── graph_utils.py              # Graphiti utilities
│   ├── providers.py                # LLM provider abstraction
│   ├── models.py                   # Data models
│   ├── query_quantitative_kpi.py   # Predefined quantitative KPI queries
│   └── query_qualtitative_kpi.py   # Predefined qualitative KPI queries
├── ingestion/                      # Ingestion Process
│   ├── ingest.py                   # Main ingestion pipeline
│   ├── pdf_parse.py                # LlamaParse PDF extraction
│   ├── data_prep.py                # Data preparation utilities
│   ├── chunker.py                  # Text chunking with LangChain
│   ├── embedder.py                 # Embedding generation
│   ├── graph_builder.py            # Graphiti knowledge graph
│   ├── vector_db_builder.py        # Weaviate vector store
│   ├── pdf_to_ingest/              # Input: PDF files to parse
│   └── json_to_ingest/             # Parsed JSON documents
├── evaluation/                     # Evaluation notebooks for answer quality assessment
│   ├── eval_ragas.ipynb            # RAGAS framework evaluation (faithfulness, relevancy)
│   ├── eval_aga.ipynb              # Agent Goal Accuracy and combined derivation evaluation metrics
│   ├── citation_accuracy_evaluation.ipynb  # Source citation accuracy
│   └── eval_visuals_tables.ipynb   # Visual analysis and result tables
├── env.example                     # Environment template
├── requirements.txt                # Python dependencies
└── README.md
```

## Documentation

- [Agent Module](agent/00AGENT_MODULE.md) - Core agent utilities, tools, and models
- [Ingestion Pipeline](ingestion/ingestion_pipeline.md) - Detailed ingestion documentation
- [Multi-Agent Architecture](agent/multi_agent/00MULIT_AGENT_ARCHITECTURE.md) - Multi-agent system design
- [Single-Agent Architecture](agent/single_agent/00SINGLE_AGENT_ARCHITECTURE.md) - Single-agent system design

##  Disclaimer

This system provides a **general-purpose framework** for financial document analysis. The following aspects require customization and refinement for production use:

### System Instructions & Prompts
- Agent prompts and system instructions (`agent/*/prompt_*`) are tailored for generic financial documents
- **You can adapt these prompts** to your specific company domain, industry standards, and reporting conventions
- Different industries (banking, manufacturing, retail, etc.) have distinct KPI definitions and risk factors

### KPI Definitions & Calculation Formulas
- Predefined KPI queries (`agent/query_quantitative_kpi.py`, `agent/query_qualitative_kpi.py`) are illustrative examples
- **Financial metrics and calculation formulas vary** by company, industry, and accounting standards (IFRS vs. GAAP, etc.)
- The calculation tools in both `agent/single_agent/` and `agent/multi_agent/derived_kpi_agent.py` implement generic financial formulas and **must be customized** with company-specific calculation logic, as well as the system instructions for single agent and derived_kpi_agent
- Manual review and validation of extracted KPIs is **strongly recommended** before using results in decision-making

---


