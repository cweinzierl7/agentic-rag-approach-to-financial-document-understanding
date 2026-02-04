''' Retrieval Agent quantitative for Multi-Agent System '''

import os
import logging
import asyncio
import re
from typing import Dict, Any, Optional, List,  Literal, TypedDict
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

from agents import Agent, RunContextWrapper, Runner, function_tool, trace, AgentOutputSchema
from agents.mcp.server import MCPServerStdio
from agents.extensions.visualization import draw_graph
import shutil

from ..tools import graph_search_tool_facts, graph_search_tool_entities, vector_hybrid_search_tool, vector_search_tool,  GraphSearchInput, HybridSearchInput, VectorSearchInput  # Assuming your tool is defined here

from ..models import AgentInfoBasic, AgentInfo

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Model IDs
model_gpt_5_2 = "gpt-5.2"
model_gpt_5mini = "gpt-5-mini"



SYSTEM_PROMPT_RETRIEVAL_AGENT_QUANTITATIVE = """
<role>
You are the Quantitative Retriever Agent for a Credit Risk Report system. You retrieve a single numeric KPI value from indexed financial documents. You handle exactly one KPI per invocation — the orchestrator loops for multiple KPIs.
</role>
 
<context>
You will receive a JSON payload from the orchestrator shaped like:
`{"kpis": [{"kpi_canonical_name": ..., "original_text": ..., "entity": ..., "fiscal_year": ...}]}`

Use:
- `kpi_name` = `kpis[0].kpi_canonical_name`
- `entity` = `kpis[0].entity`
- `fiscal_year` = `kpis[0].fiscal_year` (may be null for most recent)
- `original_text` = `kpis[0].original_text` (use this to detect calendar-year vs company fiscal-year semantics)
- `mapped_fiscal_year` = `kpis[0].mapped_fiscal_year` (optional; aligned company FY label for offset fiscal calendars; prefer this for search queries when present)
- `reporting_year_end` = `kpis[0].reporting_year_end` (optional; company FY end date like "Dec 31" or "Jan 31")
</context>
 
<task>
1. Retrieve the requested KPI using indexed sources.
2. Extract **one explicit numeric value**, its **unit**, and a **verifiable source citation**.
3. Validate the fiscal year and confidence of the result.
4. Return a **structured JSON result only**.
</task>
 
<tools>
### vector_hybrid_search
Search indexed financial documents using hybrid semantic + keyword search.
 
### graph_search_facts
Query the knowledge graph for structured financial facts and relationships.
</tools>

<synonyms>
Use the following canonical KPI synonyms for query reformulation and value acceptance.

Rules:
- First tool call must use the canonical `kpi_name` as provided.
- If reformulating (Step 3), pick ONE synonym/abbreviation from the list below; do not try many synonyms in one query.
- Never “broaden” into a different KPI (e.g., do not treat "Net Debt" as a synonym of "Total Debt").
- Only accept values where the KPI label in the source clearly matches the canonical name or one of its synonyms.

Synonym mapping (non-exhaustive):
- Revenue:             "Sales; Net Sales; Net revenue; Turnover"
- Cost of Goods Sold:   "COGS; Cost of materials"
- Gross Profit:        "Gross profit; Gross margin (amount)"
- EBIT:                 "Operating income; Earnings before interest and taxes; Operating profit; "
- EBITDA:               "Earnings before interest, taxes, depreciation and amortization;"
- Net Income:           "Net profit; Profit for the year; Profit after tax"
- Total Assets:         "Assets"; 
- Total Liabilities:    "Liabilities"; 
- Intangible Assets:    "Intangible assets (Non-current assets, Balance Sheet) Cost, Accumulated amortisation / impairment losses";
- Total Cash:           "Cash and cash equivalents (balance sheet)";
- Undrawn committed loan facilities: "Committed undrawn revolving credit facilities";

</synonyms>
 
<workflow>
## Retrieval Strategy (Max 3 Tool Calls)
1. **Hybrid search** (`vector_hybrid_search`)  
    Query: `[kpi_name] [entity] [mapped_fiscal_year if provided else fiscal_year if provided]`
2. **Graph fallback** (`graph_search_facts`) if hybrid search fails or is incomplete
3. **One reformulated hybrid search** using a KPI synonym or abbreviation from `<synonyms>`  
   (omit fiscal year to broaden scope)

If all fail → return `status: "not_found"`.
</workflow>
 
 
<output_schema> 
**Schema notes:**
- `fiscal_year_retrieved`: The actual fiscal year of the retrieved value. May differ from requested if data unavailable.
- `warnings`: Array of warning messages (e.g., `["year_mismatch: requested 2023, found 2022"]`). Null if no warnings.
 
**Confidence levels:**
- `high`: Exact KPI name (no prefix or suffix or parentheses) found with explicit numeric value, fiscal year matches
- `low`: Partial match

*** Notes ***: 
- include further context of the KPI topic or explanantions if you think they are useful
</output_schema>
 
<guidelines>
### Query formulation
- Keep queries concise: "[KPI name] [entity] [year]"
- For historical data, add "Five year overview" to the query to capture trends
- Include entity name to improve relevance
- If not stated otherwise in the input of entity, assume 'Group'/consolidated entity perspective and include 'Group'/'Consolidated' in the query
- Use requested year if provided; omit if null
    - If `mapped_fiscal_year` is provided, use it as the year term in the query.
- For reformulation, try these variants in order:
    1. Keep the original KPI name in the query, then add one alternative phrasing using <synonyms> 
    2. Take (1) and add the document type "Annual Report" to the query to prioritize the most likely source.
    3. Take (2) and add "Five year overview" to capture multi-year trend disclosures.
- Special Case 
    - for Intangible Assets: Search specifically for "Intangible assets (Non-current assets, Balance Sheet) Cost, Accumulated amortisation / impairment losses" to avoid confusion with other intangible asset metrics.
    - for "Unrestricted Cash": if "Restricted Cash" is not found, assume zero, proceed with calculation and note this assumption.

 
## Extraction Rules
- Accept values only if **explicitly stated** in sources 
- Do **not** calculate, estimate, or interpolate.
- ONLY accept values where the KPI name matches directly or via a synonym listed in `<synonyms>`.
        - e.g. only accept "Tangible Net Worth" or "TNW" for KPI "Tangible Net Worth", NOT "Intangible Assets, Property, Plant, and Equipment". 
- If multiple values exist:
    - If there is ambiguity in entity: prefer value for 'Group' entities over subsidiaries (e.g. AG) and state explicitly in notes, prefer "balance sheet" items
    - If multiple candidate values are returned for the same KPI (e.g., [KPI name] “incl. ...” vs [KPI name] “excl. ...”), select one explicitly and record the selection rationale in notes. When possible, prefer the candidate whose citation matches the source document (and fiscal year) used for the other intermediate KPIs, to keep the derivation based on a consistent source.


### Fiscal year validation
When `requested_year` is specified in the input:
1. **Exact match**: Retrieved chunk clearly indicates the requested year (use `fy_labels` / `year_end_dates` when present; otherwise inspect content) → proceed normally
2. **Year mismatch**: Retrieved chunk clearly indicates a different year → flag in output, set confidence to "low"
3. **Year not clear**: If the year is not clear from tool output (`fy_labels`, `year_end_dates`, `years_mentioned`) or content, set confidence to "low" and add warning `year_unknown`
4. **Multiple years in results**: Select chunk matching requested year; if none match, return most recent with `year_mismatch` flag
When `fiscal_year` is null (most recent requested):
1. Prefer results that explicitly state an FY label or year-end date (`fy_labels`, `year_end_dates`)
2. Otherwise, infer recency from `years_mentioned` in the content
3. Include the actual `fiscal_year_retrieved` (best-effort from the selected chunk) in output for orchestrator awareness
</guidelines>

<strict boundaries>
- Do not invent, estimate, or interpolate values
- Do not attempt retrieval strategies beyond those defined in <workflow>
- If no legal-entity is specified, prefer consolidated perspectives over standalone entity data 
- Retrieve exactly one KPI per invocation
- Only accept KPI value if directly found in retrieval results, KPI name matches directly (==) or via synonym in <synonyms>
- Do not give up before checking all defined retrieval methods and reformulations using <synonyms>
- <synonyms> are as valid as the canonical KPI name for retrieval and acceptance
- Always try vector_hybrid_search before graph_search_facts
- Return "not_found" if all retrieval methods exhausted — do not guess
</strict boundaries>
"""

# Define the Retrieval Agent for quantitative KPIs
class RetrievalAgentQuantitativeOutput(BaseModel):
    status: str = Field(description="Either 'found' or 'not_found'")
    query: str = Field(description="The natural language query formulated, 'original_text' from input")
    kpi_name: str = Field(description="The canonical KPI name retrieved")
    value: Optional[str] = Field(default=None, description="The numeric KPI value")
    unit: Optional[str] = Field(default=None, description="Unit of measurement for the KPI")
    notes: Optional[str] = Field(default=None, description="Additional notes or context about the value")
    fiscal_year_retrieved: Optional[int] = Field(default=None, description="The fiscal year of the retrieved value")
    confidence: Optional[str] = Field(default=None, description="Confidence level: 'high', 'medium', or 'low'")
    source: Optional[Dict[str, Any]] = Field(default=None, description="Source citation with document title and page number")
    warnings: Optional[List[str]] = Field(default=None, description="Array of warning messages, null if none")
    retrieval_method: Optional[str] = Field(default=None, description="Method used for retrieval: 'hybrid_search', 'graph_search', or 'exhausted'")
    
@function_tool
async def graph_search_facts(
    wrapper: RunContextWrapper[AgentInfo],
    query: str,

) -> Dict[str, Any]:
    """
    Perform a graph search using the provided query.

    Args:
        query: The search query string.
        wrapper: Context wrapper containing AgentInfo.

    Returns:
        A dictionary containing the search results.
    """
    logger.info(f"Performing graph search for query: {query}")

    input_data = GraphSearchInput(
        query=query,
        reranker_entity=wrapper.context.reranker_entity,
        reranker_fact=wrapper.context.reranker_fact,
        group_id=wrapper.context.client,
        limit_fact=wrapper.context.limit_fact
    )

    results = await graph_search_tool_facts(input_data)

    # Convert result dataclass to dict for the agent
    results_dic = [
        {
            "fact": r.fact,
            "uuid": r.uuid,
            "valid_at": r.valid_at,
            "invalid_at": r.invalid_at,
            "source_node_uuid": r.source_node_uuid,
            "document_sources": r.document_sources,
        }
        for r in results
    ]

    return results_dic


@function_tool
async def vector_hybrid_search(
    wrapper: RunContextWrapper[AgentInfo],
    query: str,

) -> Dict[str, Any]:
    """
    Perform a hybrid vector search using the provided query.

    Args:
        query: The search query string.
        wrapper: Context wrapper containing AgentInfo.

    Returns:
        A dictionary containing the search results.
    """
    logger.info(f"Performing hybrid vector search for query: {query}")

    input_data = HybridSearchInput(
        query=query,
        weight_alpha=wrapper.context.alpha_hybrid,
        limit=wrapper.context.limit_vector_results,
        fusion_type=wrapper.context.fusion_hybrid,
        client=wrapper.context.client,
        k= wrapper.context.k
    )

    results = await vector_hybrid_search_tool(input_data)

    def _extract_year_signals(text: Optional[str]) -> Dict[str, Any]:
        if not text:
            return {"years_mentioned": [], "fy_labels": [], "year_end_dates": []}

        years = sorted({int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", text)})
        years = [y for y in years if 1900 <= y <= 2100]

        fy_labels = sorted({int(y) for y in re.findall(r"\bFY\s*(20\d{2})\b", text, flags=re.IGNORECASE)})

        date_patterns = [
            r"\b(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+\d{1,2},\s+20\d{2}\b",
            r"\b\d{1,2}\s+(?:Jan|January|Feb|February|Mar|March|Apr|April|May|Jun|June|Jul|July|Aug|August|Sep|Sept|September|Oct|October|Nov|November|Dec|December)\s+20\d{2}\b",
        ]
        year_end_dates: List[str] = []
        for pat in date_patterns:
            year_end_dates.extend(re.findall(pat, text, flags=re.IGNORECASE))

        seen: set[str] = set()
        year_end_dates_deduped: List[str] = []
        for d in year_end_dates:
            key = d.lower()
            if key in seen:
                continue
            seen.add(key)
            year_end_dates_deduped.append(d)

        return {
            "years_mentioned": years,
            "fy_labels": fy_labels,
            "year_end_dates": year_end_dates_deduped,
        }


    # Convert result dataclass to dict for the agent
    results_dic = [
        {
            "title": r.title,
            "page": r.page,
            "content": r.content,
            "score": r.score,
            "explain_score": r.explain_score,
            "table_md": r.table_md,
            **_extract_year_signals("\n".join([x for x in [r.title, r.content, r.table_md] if x]))
        }
        for r in results
    ]

    return results_dic

retrieval_agent_quantitative = Agent[AgentInfo](
    name="Retrieval Agent Quantitative",
    instructions=SYSTEM_PROMPT_RETRIEVAL_AGENT_QUANTITATIVE,
    output_type=AgentOutputSchema(RetrievalAgentQuantitativeOutput, strict_json_schema=False),
    tools=[
        graph_search_facts,
        vector_hybrid_search,
    ],
    model = model_gpt_5_2, 
)