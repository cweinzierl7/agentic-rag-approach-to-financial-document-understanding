# Single Agent Architecture

## Overview

The single agent architecture is a unified, end-to-end agentic RAG (Retrieval-Augmented Generation) system designed to extract and compute KPIs (Key Performance Indicators) from financial documents. It combines vector search, knowledge graph retrieval, and tool-based calculations in a single orchestrated flow.

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    Single Agent System                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Query Input (KPI Questions)               │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │           Single LLM-Powered Agent                      │  │
│  │   (Analyzes query, decides tool calls, orchestrates)    │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│   ┌─────────────┼─────────────┬──────────────┐                 │
│   │             │             │              │                 │
│   ▼             ▼             ▼              ▼                 │
│  ┌────────┐ ┌────────┐ ┌─────────────┐ ┌──────────────┐       │
│  │Vector  │ │Graph   │ │Graph        │ │KPI          │       │
│  │Hybrid  │ │Search  │ │Search       │ │Calculator   │       │
│  │Search  │ │Facts   │ │Entities     │ │Tool         │       │
│  └────────┘ └────────┘ └─────────────┘ └──────────────┘       │
│      │          │            │              │                  │
│      └──────────┴────────────┴──────────────┘                  │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │      Result Formatting & Markdown Generation            │  │
│  └──────────────┬───────────────────────────────────────────┘  │
│                 │                                               │
│                 ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │    Markdown Output (agent/outputs/)                     │  │
│  │    - KPI Values & Calculations                          │  │
│  │    - Qualitative Responses                              │  │
│  │    - Source Citations                                   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. **Single Agent** (`single_agent.py`)
The main orchestrator that:
- Accepts user queries (quantitative and qualitative KPI questions)
- Decides which tools to call and in what order
- Processes results and formats outputs
- Manages context and conversation flow

**Key Functions:**
- `main()` - Entry point that initializes databases and runs the agent
- `format_kpis_markdown()` - Formats KPI results into markdown
- KPI query builders for speedboat and consolidated metrics

### 2. **Retrieval Tools** (`tools.py`)

#### Vector/Hybrid Search
- **Purpose:** Retrieve relevant document chunks using semantic similarity
- **Input:** Query string, search parameters (alpha, limit, fusion type)
- **Output:** List of chunks with score, page number, document title
- **Usage:** Finding quantitative data (numbers, financial metrics)

#### Graph Search - Facts
- **Purpose:** Query the knowledge graph for specific facts
- **Input:** Query string, reranker type, group IDs
- **Output:** List of facts with confidence scores and document sources
- **Usage:** Finding qualitative statements and relationships

#### Graph Search - Entities
- **Purpose:** Retrieve named entities (companies, people, locations)
- **Input:** Entity query, reranker settings
- **Output:** Entity names, summaries, document sources
- **Usage:** Entity resolution and context gathering

#### KPI Calculator Tool
- **Purpose:** Compute derived KPIs from intermediate values
- **Input:** Intermediate KPI values (revenue, COGS, assets, liabilities, etc.)
- **Output:** Calculated KPI with formula used and metadata
- **Usage:** Computing metrics like Gross Profit, Tangible Net Worth, etc.

### 3. **Data Storage Layer**

#### Vector Database (Weaviate)
- Stores embeddings of document chunks
- Supports hybrid (vector + BM25) search
- Organized by document, page, and client

#### Knowledge Graph (Neo4j)
- Stores entities and facts as graph nodes/edges
- Supports semantic queries
- Maintains relationships between concepts and documents

### 4. **Output Management**
- Generates markdown files with timestamped filenames
- Includes KPI values, sources, and explanatory notes
- Saves to `agent/outputs/` directory

## Data Flow

```
User Query
    ↓
Agent Instruction Processing
    ↓
Tool Selection & Execution
    ├─→ Vector Search (if quantitative)
    ├─→ Graph Search (if qualitative/entity)
    └─→ KPI Calculator (if derivable)
    ↓
Result Aggregation
    ↓
Markdown Formatting
    ↓
File Output
```

## Query Types Supported

### Quantitative Queries
- "What is the EBITDA of RWE in 2024?"
- "What is the total debt?"
- "Provide gross profit margins"

**Processing:**
1. Query vector search for numbers and financial metrics
2. If exact values not found, call KPI calculator with raw inputs
3. Format results with units and explanations

### Qualitative Queries
- "What is RWE's growth strategy?"
- "What are the main risks?"
- "Provide a SWOT analysis"

**Processing:**
1. Query graph for facts and entities
2. Retrieve relevant narratives from documents
3. Synthesize into coherent qualitative response

## Configuration & Parameters

### Agent Configuration (`agent/models.py`)
```python
AgentInfo:
  - client: Default client identifier
  - reranker_entity: Reranking algorithm for entities 
  - reranker_fact: Reranking algorithm for facts
  - limit_vector_results: Max results from vector search
  - alpha_hybrid: Weight for hybrid search (0.75 = 75% semantic, 25% keyword)
  - limit_fact: Max facts returned 
  - limit_entity: Max entities returned 
  - k: Window size for sentence window retrieval 
```

### System Prompt (`prompt_single_agent.py`)
- Instructs agent on KPI extraction behavior
- Defines tool usage guidelines
- Specifies query interpretation rules
- Controls formatting and citation requirements

## Key Features

1. **Flexible Tool Usage**: Agent autonomously decides which tools to call
2. **Multi-Source Retrieval**: Combines vector, graph, and calculated results
3. **Source Citation**: All results include document source and page number
4. **Error Handling**: Graceful degradation when data is unavailable
5. **Scalable Output**: Markdown format supports complex formatting and tables

## Running the Single Agent

```bash
# From project root with venv activated
python -m agent.single_agent
```

**Output:**
- Console logs of agent decisions and tool calls
- Markdown file saved to `agent/outputs/single_agent_response_[timestamp].md`

## Limitations & Considerations

1. **LLM Stochasticity**: Results may vary based on model temperature and randomness
2. **Tool Availability**: Requires running Weaviate and Neo4j instances
3. **Context Window**: Long documents may exceed token limits
4. **Derived KPIs**: Requires pre-defined formulas and intermediate data availability
5. **Accuracy**: Depends on document quality and embedding model performance

## Future Enhancements

- Multi-turn conversation support with memory
- Confidence scoring for retrieved results
- Interactive clarification when ambiguity exists
- Custom formula definitions per domain
- Real-time data integration
