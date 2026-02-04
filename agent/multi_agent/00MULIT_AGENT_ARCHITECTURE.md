# Multi-Agent Architecture Proposal

## Executive Summary

This document proposes a multi-agent architecture for an automated Credit Risk Report system. The system retrieves Key Performance Indicators (KPIs) from indexed financial documents and produces structured credit risk reports.

Rather than implementing this as a single monolithic agent, we decompose the system into five specialized agents coordinated by a lightweight Python orchestrator. This design improves accuracy, maintainability, and observability while keeping each component focused and testable.

---

## 1. Problem Statement

### What the System Does

The Credit Risk Report Agent receives user queries requesting:

- **Quantitative KPIs**: Specific financial metrics (e.g., EBITDA, Gross Profit)
- **Qualitative Assessments**: Thematic information (e.g., industry outlook, risk factors)

The system retrieves this information from two data sources:

| Source | Content | Access Method |
|--------|---------|---------------|
| **Hybrid Store** | Chunked financial documents (e.g. annual reports) | Semantic + keyword search |
| **Graph Knowledge Base** | Structured entity relationships and facts | Entity and fact queries |

### Why a Single Agent Is Insufficient

A monolithic agent attempting to handle all responsibilities faces several challenges:

| Challenge | Impact |
|-----------|--------|
| **Prompt complexity** | A single prompt exceeds 800+ lines, mixing query classification, retrieval strategies, fallback logic, and output formatting |
| **Context dilution** | LLMs exhibit "middle blindness" — important instructions get lost in lengthy prompts |
| **Debugging difficulty** | When retrieval fails, it's unclear which stage caused the failure |
| **Rigid coupling** | Changing retrieval strategy requires editing the entire prompt |
| **Testing burden** | Cannot unit test individual capabilities in isolation |

---

## 2. Architecture Overview

### System Flow

```
                              User Query
                                  │
                                  ▼
                    ┌───────────────────────┐
                    │     ROUTER AGENT      │
                    │  ───────────────────  │
                    │  • Classify query     │
                    │  • Extract entity     │
                    │  • Decompose KPIs     │
                    └───────────┬───────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │  ORCHESTRATOR (Python)│
                    │  ───────────────────  │
                    │  • Route by category  │
                    │  • Loop for multi-KPI │
                    │  • Handle fallbacks   │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
┌───────────────┐     ┌─────────────────┐     ┌───────────────┐
│ QUANTITATIVE  │     │  DERIVED-KPI    │     │  QUALITATIVE  │
│ RETRIEVER     │     │  RETRIEVER      │     │  RETRIEVER    │
│ ───────────── │     │  ───────────────│     │ ───────────── │
│ Direct KPI    │     │ Fallback when   │     │ Thematic      │
│ retrieval     │     │ direct fails    │     │ extraction    │
└───────┬───────┘     └────────┬────────┘     └───────┬───────┘
        │                      │                      │
        │               ┌──────┴──────┐               │
        │               │ Uses as tool│               │
        │               ▼             │               │
        │      ┌───────────────┐      │               │
        │      │ QUANTITATIVE  │      │               │
        │      │ RETRIEVER     │      │               │
        │      └───────────────┘      │               │
        │                             │               │
        └──────────────┬──────────────┴───────────────┘
                       │
                       ▼
             ┌───────────────────┐
             │  Writer           │
             │  AGENT            │
             │  ─────────────────│
             │  Format final     │
             │  markdown report  │
             └───────────────────┘
                       │
                       ▼
                 Credit Risk Report
                   (Markdown)
```

### Agent Inventory

| Agent | Responsibility | Tools | Invocation |
|-------|----------------|-------|------------|
| **Router** | Query classification, entity extraction, KPI decomposition | None | Always first |
| **Quantitative Retriever** | Single KPI value retrieval | `query_hybrid_store`, `graph_search_facts` | Per KPI in request |
| **Derived-KPI Retriever** | Compute KPIs from intermediates when direct retrieval fails | `retrieve_kpi` (agent-as-tool), `compute_kpi` | On retrieval failure |
| **Qualitative Retriever** | Extract thematic/narrative information | `graph_search_entities`, `graph_search_facts`, `query_hybrid_store` (fallback) | Category C queries |
| **Writer** | Validate results, format markdown report | None | Always last |

---

## 3. Agent Descriptions

### 3.1 Router Agent

**Purpose**: Analyze incoming queries to determine intent, extract context, and structure the retrieval task.

**Input**: Raw user query (natural language)

**Output**: Structured routing decision containing:
- Query category (atomic quantitative / multiple quantitative / thematic qualitative)
- Entity name and fiscal year
- List of canonical KPI names or thematic elements to retrieve

**Key Behaviors**:
- Resolves KPI synonyms to canonical names (e.g., "TNW" → "Tangible Net Worth")
- Decomposes multi-KPI requests into individual retrieval tasks
- Asks for clarification when query is ambiguous (does not guess)

**Tools**: None — pure reasoning agent

---

### 3.2 Quantitative Retriever Agent

**Purpose**: Retrieve a single quantitative KPI value from indexed documents.

**Input**: KPI name, entity, fiscal year (provided by orchestrator)

**Output**: 
- On success: `{value, unit, source citation}`
- On failure: `{status: "not_found", reason}`

**Retrieval Strategy**:
1. Query vector db with KPI name + entity context
2. If insufficient, query graph KB for structured facts
3. If no explicit value found, return "not_found"

**Tools**: 
- `query_hybrid_store` — semantic + keyword search over document chunks
- `graph_search_facts` — structured fact retrieval from knowledge graph

**Key Constraint**: Handles exactly one KPI per invocation. The orchestrator loops for multiple KPIs.

---

### 3.3 Derived-KPI Retriever Agent

**Purpose**: Handle KPIs that cannot be directly retrieved by computing them from intermediate values.

**Input**: 
- KPI name that failed direct retrieval
- Original user query phrasing (for semantic matching)
- Entity and fiscal year context

**Output**:
- On success: `{computed_value, formula_used, intermediate_values_with_sources}`
- On failure: `{status: "unavailable", reason, missing_intermediates}`

**Workflow**:
1. **Match derivation rule**: Reason about whether user's request maps to a known derivation (e.g., "EBIT to interest ratio" → Interest Coverage Ratio)
2. **Retrieve intermediates**: Call Quantitative Retriever (as tool) for each required intermediate KPI
3. **Compute result**: If all intermediates found, call `compute_kpi` tool
4. **Return with audit trail**: Include intermediate values and sources for transparency

**Tools**:
- `retrieve_kpi` — wraps Quantitative Retriever agent (agent-as-tool pattern)
- `compute_kpi` — applies predefined financial formulas

**Key Design Choice**: This agent encapsulates the entire fallback workflow. The orchestrator simply calls it when direct retrieval fails — no complex conditional logic in the orchestrator.

---

### 3.4 Qualitative Retriever Agent

**Purpose**: Extract thematic, narrative information for qualitative assessments.

**Input**: List of thematic elements to extract (e.g., "industry outlook", "risk factors"), entity context

**Output**: Array of extracted elements, each with:
- Thematic element name
- Synthesized content (2-4 sentences)
- Source citation
- Confidence level

**Retrieval Strategy**:
1. Query graph KB for entity relationships (`graph_search_entities`)
2. Query graph KB for relevant facts (`graph_search_facts`)
3. **Fallback**: If graph yields insufficient results, query hybrid store (`query_hybrid_store`)

**Tools**:
- `graph_search_entities` — retrieve entity nodes and properties
- `graph_search_facts` — retrieve relationship-based facts
- `query_hybrid_store` — fallback to document chunks

**Key Behavior**: Synthesizes information into concise summaries rather than returning raw text.

---

### 3.5 Writer Agent

**Purpose**: Assemble retrieval results into a formatted credit risk report.

**Input**: Collection of results from upstream retrievers

**Output**: Markdown-formatted financial report with:
- Structured KPI tables
- Qualitative assessment sections
- Source citations
- Data gap indicators

**Key Behaviors**:
- Validates completeness (all requested items have results)
- Standardizes formatting (units, decimal places)
- Applies financial document conventions (section headers, table layouts)
- Does NOT interpret or analyze — presents facts only

**Tools**: None — pure formatting/validation agent

---

## 4. Design Rationale

### Why Multi-Agent for Credit Risk Reporting?

The credit risk report use case exhibits multiple complexity characteristics that justify a multi-agent approach:

| Complexity Marker | How It Manifests | Design Response |
|-------------------|------------------|-----------------|
| **Diverse Expertise** | Query classification requires linguistic reasoning; retrieval requires search optimization; derivation requires financial domain knowledge; formatting requires document structure expertise | Separate agents with focused prompts |
| **Extensive Context** | KPI taxonomy, derivation rules, synonym mappings, output schemas — too much for one prompt | Each agent loads only relevant context |
| **Conditional Workflows** | Direct retrieval → fallback to derivation → mark unavailable | Orchestrator handles control flow; agents handle cognition |
| **Multiple Data Sources** | Hybrid store for documents; Graph KB for structured facts | Different retrievers optimized for different sources |

### Why This Specific Decomposition?

**Router as Entry Point**
- Centralizes query understanding
- Enables consistent entity extraction
- Prevents downstream agents from redundant parsing

**Separate Quantitative vs. Qualitative Retrievers**
- Different retrieval strategies (precise KPI lookup vs. broad thematic search)
- Different tool preferences (hybrid store vs. graph KB)
- Different output structures (numeric values vs. narrative summaries)

**Derived-KPI Retriever with Agent-as-Tool Pattern**
- Encapsulates fallback complexity
- Reuses Quantitative Retriever without code duplication
- Keeps orchestrator logic simple

**Writer as Final Stage**
- Single point for output formatting
- Consistent report structure regardless of retrieval path
- Clear separation between retrieval and presentation

---

## 5. Data Flow Example

**User Query**: "Get me the Gross Profit and SWOT Analysis for Northwind Energy AG FY2023"

### Step 1: Router Agent

**Output** (`RouterAgentOutput`):
```json
{
  "status": "ready",
  "entity": "Northwind Energy AG",
  "kpi_name": ["Gross Profit", "SWOT Analysis"],
  "requested_year": 2023,
  "fiscal_year_basis": "company_fy",
  "mapped_fiscal_year": 2023,
  "reporting_year_end": "Dec 31",
  "category": "mixed",
  "quantitative_items": [
    {
      "kpi_canonical_name": "Gross Profit",
      "synonyms_matched": [],
      "original_text": "Gross Profit for Northwind Energy AG FY2023"
    }
  ],
  "qualitative_items": [
    {
      "kpi_canonical_name": "SWOT Analysis",
      "synonyms_matched": [],
      "original_text": "SWOT Analysis for Northwind Energy AG FY2023"
    }
  ],
  "reason": null,
  "suggested_questions": null
}
```

### Step 2: Orchestrator Routes

1. For "Gross Profit" → call Quantitative Retriever
2. For "SWOT Analysis" → call Qualitative Retriever

### Step 3: Quantitative Retriever (Gross Profit)

- Calls `vector_hybrid_search("Gross Profit Northwind Energy AG 2023")`
- Found explicit value in Annual Report

**Output** (`RetrievalAgentQuantitativeOutput`):
```json
{
  "status": "found",
  "query": "Gross Profit for Northwind Energy AG FY2023",
  "kpi_name": "Gross Profit",
  "value": "8,742",
  "unit": "EUR million",
  "notes": "Consolidated Group figure from income statement",
  "fiscal_year_retrieved": 2023,
  "confidence": "high",
  "source": {
    "document": "Northwind_Energy_Annual_Report_2023.pdf",
    "pages": [112]
  },
  "warnings": null,
  "retrieval_method": "hybrid_search"
}
```

### Step 4: Qualitative Retriever (SWOT Analysis)

- Calls `graph_search_entities("Northwind Energy AG")` → retrieves sector, market position
- Calls `graph_search_facts("Northwind Energy AG strengths weaknesses opportunities threats")` → retrieves strategic factors
- Calls `vector_hybrid_search("Northwind Energy strategic position risks opportunities")` → fallback for additional context

**Output** (`RetrievalAgentQualitativeOutput`):
```json
{
  "status": "found",
  "query": "SWOT Analysis for Northwind Energy AG FY2023",
  "kpi_name": "SWOT Analysis",
  "themes": "strengths, weaknesses, opportunities, threats, strategic position",
  "entity": "Northwind Energy AG",
  "notes": "Synthesized from annual report strategic sections and knowledge graph",
  "summary": "**Strengths**: Leading position in European renewable energy market; diversified generation portfolio across wind, solar, and conventional assets; strong balance sheet with investment-grade credit rating. **Weaknesses**: Exposure to volatile commodity prices; legacy coal assets requiring phase-out investments; regulatory dependency in core markets. **Opportunities**: Accelerating energy transition in Europe; expansion of offshore wind capacity; growing demand for green hydrogen infrastructure. **Threats**: Increasing competition from new market entrants; policy uncertainty around energy subsidies; supply chain constraints for renewable components.",
  "findings": [
    {
      "type": "fact",
      "content": "Northwind Energy holds leading market position in European offshore wind development",
      "source": {"document_title": "Northwind_Energy_Annual_Report_2023.pdf", "page_number": 24}
    },
    {
      "type": "fact",
      "content": "Coal phase-out commitments require significant capital reallocation",
      "source": {"document_title": "Northwind_Energy_Annual_Report_2023.pdf", "page_number": 31}
    },
    {
      "type": "entity_property",
      "content": "Investment-grade credit rating maintained (Baa2/BBB)",
      "source": {"document_title": "Northwind_Energy_Annual_Report_2023.pdf", "page_number": 89}
    }
  ],
  "confidence": "high",
  "entity_candidates": null,
  "clarification_question": null
}
```

### Step 5: Writer Agent

**Input**: Collection of `RetrievalAgentQuantitativeOutput` and `RetrievalAgentQualitativeOutput` results

**Output** (`ReportOutput`):
```json
{
  "report": "# Credit Risk Report: Northwind Energy AG\n\n**Reporting Period:** FY2023\n**Report Generated:** 2024-01-15\n**Data Completeness:** 2 of 2 KPIs retrieved\n\n---\n\n## Executive Summary\nNorthwind Energy AG reported Gross Profit of EUR 8,742 million for FY2023. The company maintains a strong market position in European renewable energy with an investment-grade credit rating.\n\n---\n\n## Quantitative Metrics\n\n### Financial KPIs\n| KPI | FY2023 | Notes | Source |\n|-----|--------|-------|--------|\n| Gross Profit | 8,742 EUR million | Consolidated Group figure | Northwind_Energy_Annual_Report_2023.pdf, p.112 |\n\n---\n\n## Qualitative Assessment\n| KPI | Content | Notes | Source |\n|-----|---------|-------|--------|\n| SWOT Analysis | **Strengths**: Leading position in European renewable energy market; diversified generation portfolio across wind, solar, and conventional assets; strong balance sheet with investment-grade credit rating. **Weaknesses**: Exposure to volatile commodity prices; legacy coal assets requiring phase-out investments; regulatory dependency in core markets. **Opportunities**: Accelerating energy transition in Europe; expansion of offshore wind capacity; growing demand for green hydrogen infrastructure. **Threats**: Increasing competition from new market entrants; policy uncertainty around energy subsidies; supply chain constraints for renewable components. | Synthesized from strategic sections | Northwind_Energy_Annual_Report_2023.pdf, pp.24,31,89 |\n\n---\n\n## Credit Risk Assessment\nNorthwind Energy AG demonstrates stable credit fundamentals with strong profitability and a leading position in the European energy transition. The investment-grade credit rating reflects adequate financial flexibility. Key risks include commodity price volatility and regulatory uncertainty. Credit Risk Score: 3/10 (low risk).\n\n---\n*Sources: Northwind_Energy_Annual_Report_2023.pdf*",
  "data_quality_notes": null
}
```

**Rendered Report:**

```markdown
# Credit Risk Report: Northwind Energy AG

**Reporting Period:** FY2023  
**Report Generated:** 2024-01-15  
**Data Completeness:** 2 of 2 KPIs retrieved

---

## Executive Summary
Northwind Energy AG reported Gross Profit of EUR 8,742 million for FY2023. The company maintains a strong market position in European renewable energy with an investment-grade credit rating.

---

## Quantitative Metrics

### Financial KPIs
| KPI | FY2023 | Notes | Source |
|-----|--------|-------|--------|
| Gross Profit | 8,742 EUR million | Consolidated Group figure | Northwind_Energy_Annual_Report_2023.pdf, p.112 |

---

## Qualitative Assessment
| KPI | Content | Notes | Source |
|-----|---------|-------|--------|
| SWOT Analysis | **Strengths**: Leading position in European renewable energy market; diversified portfolio. **Weaknesses**: Commodity price exposure; coal phase-out costs. **Opportunities**: Energy transition; offshore wind expansion. **Threats**: Competition; regulatory uncertainty. | Synthesized from strategic sections | Northwind_Energy_Annual_Report_2023.pdf, pp.24,31,89 |

---

## Credit Risk Assessment
Northwind Energy AG demonstrates stable credit fundamentals with strong profitability and a leading position in the European energy transition. The investment-grade credit rating reflects adequate financial flexibility. Key risks include commodity price volatility and regulatory uncertainty. Credit Risk Score: 3/10 (low risk).

---
*Sources: Northwind_Energy_Annual_Report_2023.pdf*
```

---

## 6. Trade-offs & Considerations

### What This Design Optimizes For

| Benefit | Mechanism |
|---------|-----------|
| **Accuracy** | Focused prompts reduce instruction dilution |
| **Debuggability** | Clear trace: Router → Retriever → Synthesizer |
| **Testability** | Each agent can be unit tested with mocked inputs |
| **Maintainability** | Change retrieval strategy without touching classification logic |
| **Extensibility** | Add new KPI types by updating Router taxonomy and derivation rules |

### What This Design Does NOT Optimize For

| Trade-off | Mitigation |
|-----------|------------|
| **Latency** | Sequential agent calls add overhead; can parallelize independent retrievals |
| **Orchestrator complexity** | Kept minimal (~50 lines Python); could grow with edge cases |
| **Token cost** | Multiple LLM calls; partially offset by shorter prompts per call |


