# Agent Module

This module contains the core infrastructure for the agentic RAG system, including utilities for knowledge graph operations, vector database search, LLM providers, data models, and predefined KPI queries.

For specific agent architecture documentation, see:
- [Single-Agent Architecture](single_agent/00SINGLE_AGENT_ARCHITECTURE.md)
- [Multi-Agent Architecture](multi_agent/00MULIT_AGENT_ARCHITECTURE.md)

---

## Module Overview

| File | Description |
|------|-------------|
| `graph_utils.py` | Graphiti/Neo4j knowledge graph client and search functions |
| `vector_db_utils.py` | Weaviate vector database schema and search utilities |
| `tools.py` | Search tool definitions used by agents |
| `providers.py` | LLM and embedding provider configuration |
| `models.py` | Pydantic data models for validation and serialization |
| `query_quantitative_kpi.py` | Predefined quantitative KPI query templates |
| `query_qualtitative_kpi.py` | Predefined qualitative KPI query templates |

---

## graph_utils.py

Manages all interactions with the Graphiti knowledge graph built on Neo4j.

### Key Class: `GraphitiClient`

Initializes and manages the Graphiti client for knowledge graph operations.

```python
class GraphitiClient:
    def __init__(self, neo4j_uri, neo4j_user, neo4j_password)
```

**Configuration (from environment variables):**
- `NEO4J_URI` - Neo4j connection URI
- `NEO4J_USER` - Neo4j username
- `NEO4J_PASSWORD` - Neo4j password
- `LLM_API_KEY` - OpenAI API key for LLM operations

### Key Functions

| Function | Description |
|----------|-------------|
| `initialize_graph()` | Initialize the Graphiti client and connect to Neo4j |
| `close_graph()` | Close the Neo4j connection |
| `search_knowledge_graph_facts()` | Search for facts/relationships in the knowledge graph |
| `search_knowledge_graph_entities()` | Search for entities in the knowledge graph |
| `add_episode()` | Add a new episode (document chunk) to the knowledge graph |

### Search Configuration Options

Supports multiple reranking strategies:
- `RRF` - Reciprocal Rank Fusion (default)
- `MMR` - Maximal Marginal Relevance
- `CROSS_ENCODER` - Cross-encoder reranking

---

## vector_db_utils.py

Handles all Weaviate vector database operations including schema management and search.

### Key Class: `VectorDB_Schema`

Manages Weaviate collections and search operations.

```python
class VectorDB_Schema:
    def __init__(self, class_chunk="Chunks", class_fulldoc="FullDoc")
```

### Collections

**Chunks Collection** - Stores document chunks with embeddings:
- `index` - Chunk index within document
- `title` - Document title
- `source` - Source file path
- `page` - Page number
- `type` - Chunk type (text, table, etc.)
- `heading_lvl1/2/3` - Document headings hierarchy
- `content` - Chunk text content
- `md` - Markdown representation (for tables)
- `client` - Client identifier for filtering

**FullDoc Collection** - Stores full document metadata:
- `title`, `source`, `md`, `client`

### Key Functions

| Function | Description |
|----------|-------------|
| `initialize_database(basis)` | Initialize Weaviate client ("local" or "cloud") |
| `close_database()` | Close Weaviate connection |
| `search_hybrid()` | Hybrid search combining semantic + BM25 |
| `search_vector()` | Pure vector similarity search |
| `sentence_window_retrieval()` | Retrieve surrounding chunks for context |

### Hybrid Search Parameters

```python
async def search_hybrid(
    query: str,
    alpha: float = 0.75,      # Balance: 1.0 = pure vector, 0.0 = pure BM25
    limit: int = 20,
    fusion_type: str = "RELATIVE_SCORE",
    client: str = "default_client",
    k: int = 0                # Sentence window size
)
```

---

## tools.py

Defines the search tools that agents use for retrieval operations.

### Tool Input Models

```python
class HybridSearchInput(BaseModel):
    query: str
    client: str = "default_client"
    limit: int = 20
    weight_alpha: float = 0.75
    fusion_type: str = "HybridFusion.RELATIVE_SCORE"
    k: int = 0  # Sentence window chunks

class GraphSearchInput(BaseModel):
    query: str
    group_id: str = "default_client"
    reranker_entity: str = "RRF"
    reranker_fact: str = "RRF"
    limit_fact: int = 10
    limit_entity: int = 10

class VectorSearchInput(BaseModel):
    query: str
    client: str = "default_client"
    limit: int = 20
    k: int = 0
```

### Tool Functions

| Function | Description | Returns |
|----------|-------------|---------|
| `graph_search_tool_facts()` | Search knowledge graph for facts/relationships | `List[GraphSearchFactResult]` |
| `graph_search_tool_entities()` | Search knowledge graph for entities | `List[GraphSearchEntityResult]` |
| `vector_hybrid_search_tool()` | Hybrid vector + BM25 search in Weaviate | `List[VectorHybridResult]` |
| `vector_search_tool()` | Pure vector search in Weaviate | `List[VectorResult]` |
| `generate_embedding()` | Generate embeddings for text | `List[float]` |

---

## providers.py

Configures LLM and embedding providers based on environment variables.

### Functions

```python
def get_embedding_client() -> openai.AsyncOpenAI:
    """Returns configured OpenAI async client for embeddings."""

def get_embedding_model() -> str:
    """Returns embedding model name from environment."""
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_BASE_URL` | `https://api.openai.com/v1` | Embedding API base URL |
| `EMBEDDING_API_KEY` | - | API key for embeddings |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |

---

## models.py

Pydantic models for data validation, serialization, and type safety across the system.

### Ingestion Models

```python
class IngestionConfig(BaseModel):
    chunk_size: int = 400
    chunk_overlap: int = 0
    max_chunk_size: int = 2000
    chunk_separator: List[str]
    chunking_method: str = "recursive"

class IngestionResult(BaseModel):
    created_docs: List[str]
    total_chunks: int
    total_episodes: int
    processing_time_ms: float
    errors_graph: List[str]
    errors_vector_db: int
```

### Search Result Models

```python
class GraphSearchFactResult(BaseModel):
    fact: str
    uuid: str
    episode_uuids: List[str]
    document_sources: str
    valid_at: Optional[str]
    invalid_at: Optional[str]
    score: Optional[float]

class GraphSearchEntityResult(BaseModel):
    name: str
    uuid: str
    summary: str
    document_sources: str
    score: Optional[float]

class VectorHybridResult(BaseModel):
    title: str
    page: int
    content: str
    score: Optional[float]
    table_md: Optional[str]
```

### Agent Output Models

```python
class KPI_Output(BaseModel):
    kpi: str                    # KPI name
    year: Optional[int]         # Reporting year
    type: str                   # "quantitative" or "qualitative"
    value: Optional[str]        # Numeric value with unit
    response: Optional[str]     # Textual response (qualitative)
    notes: Optional[str]        # Calculation notes/formulas
    source: List[SourceDict]    # Document and page citations
    error: Optional[str]        # Error message if any
```

### Agent Configuration

```python
@dataclass
class AgentInfo:
    client: str
    reranker_entity: str
    reranker_fact: str
    limit_vector_results: int
    alpha_hybrid: float
    limit_fact: int
    limit_entity: int
    k: int
    fusion_hybrid: Optional[str]
```

---

## query_quantitative_kpi.py

Predefined query templates for quantitative (numerical) KPIs.

### Class: `QUANTITATIVE_KPIs_speedboat`

Generates year-specific queries for financial KPIs.

```python
@dataclass
class QUANTITATIVE_KPIs_speedboat:
    client: str
    
    def build_queries(self, year_basis: str, year_0: int, year_1: int, year_2: int)
```

### Supported KPIs

| KPI | Description |
|-----|-------------|
| `TOTAL_SALES_REVENUE` | Total revenue / turnover |
| `GROSS_PROFIT` | Gross profit |
| `EBITDA` | Earnings before interest, taxes, depreciation, amortization |
| `EBIT` | Earnings before interest and taxes |
| `NET_INCOME` | Net income / profit |
| `TOTAL_CASH` | Cash and cash equivalents |
| `TOTAL_EQUITY` | Total shareholders' equity |
| `TANGIBLE_NET_WORTH` | Total assets - liabilities - intangibles |
| `CAPEX` | Capital expenditures |
| `FREE_CASH_FLOW` | Operating cash flow - CapEx |
| `UNRESTRICTED_CASH` | Cash not subject to restrictions |
| `UNDRAWN_LOAN_FACILITIES` | Available credit facilities |

Each KPI supports 3 years of data (`_0`, `_1`, `_2` suffixes).

---

## query_qualtitative_kpi.py

Predefined query templates for qualitative (descriptive) KPIs.

### Class: `QualitativeKPIs_speedboat`

Generates queries for non-numerical company information.

```python
@dataclass
class QualitativeKPIs_speedboat:
    client: str
    
    def build_queries(self)
```

### Supported KPI Categories

**Company Profile:**
- `COMPANY_NAME` - Full legal name and variants
- `OWNERSHIP` - Public/private ownership type
- `MARKET_CAP` - Market capitalization
- `OWNERSHIP_STRUCTURE` - Shareholder breakdown
- `MANAGEMENT` - CEO and board members
- `HEADQUARTER` - Headquarters location
- `INDUSTRY` / `SECTOR` - Industry classification
- `EMPLOYEES` - Employee count
- `EXTERNAL_RATING` - Credit ratings

**Industry & Market:**
- `INDUSTRY_TREND` - Industry trends and growth projections
- `CYCLICALITY` - Market cycle characteristics
- `COMPETITORS` / `PEER_GROUP` - Competitive landscape
- `REGULATORY_ECONOMIC_FACTORS` - Regulatory/economic risks

**Business Model:**
- `HISTORICAL_BACKGROUND` - Company history and milestones
- `MA_HISTORY` - M&A activity
- `GEOGRAPHICAL_PRESENCE` - Geographic footprint
- `BUSINESS_SEGMENTS` - Business segment breakdown
- `PRODUCT_SERVICES` - Products and services offered
- `VALUE_CHAIN` - Value chain description
- `KEY_SUPPLIERS` - Key supplier relationships
- `TOP_CLIENTS` - Major customers
- `RISKS_MITIGATION` - Risk factors and mitigants
- `SWOT_ANALYSIS` - Strengths, weaknesses, opportunities, threats


