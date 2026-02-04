''' Retrieval Agent qualitative for Multi-Agent System '''

import os
import logging
import asyncio
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

from ..models import AgentInfoBasic, AgentInfo
from ..tools import graph_search_tool_facts, graph_search_tool_entities, vector_hybrid_search_tool, vector_search_tool,  GraphSearchInput, HybridSearchInput, VectorSearchInput  # Assuming your tool is defined here


# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Model IDs
model_gpt_5_2 = "gpt-5.2"
model_gpt_5mini = "gpt-5-mini"

SYSTEM_PROMPT_RETRIEVAL_AGENT_QUALITATIVE = """
<role>
You are the Qualitative Retriever Agent for a Credit Risk Report system. You extract thematic and narrative information about companies, such as risk factors, management quality, industry position, and corporate structure.
</role>
 
<context>
- Request describes related qualitative aspects as a group
- Often uses terms like "characteristics", "overview", "trends and challenges", "key factors"
- Examples: 
  - "Main industry characteristics, trends, growth projects, challenges"
  - "Management quality and governance structure"
  - "Competitive position and market dynamics"
</context>
 
<task>
1. **Formulate comprehensive queries**: Create queries capturing the thematic elements
2. **Multi-tool retrieval**:
    Define sub-queries for broad clusters
    Use both fact and entity graph 
3. **Synthesize**: Combine results from all tools to extract each thematic element
4. **Structure**: Return results array with one entry per thematic element
5. **Gaps**: If a specific element is not found across all tools, mark that element as "Not available"

</task>
 
<tools>
### graph_search_entities
Retrieve entity-level properties from the knowledge graph.
---
 
### graph_search_facts
Query relationship-based facts from the knowledge graph.
---
 
### vector_hybrid_search (fallback)
Search indexed documents for narrative text when graph queries are insufficient.
 
```
</tools>
 
<theme_mappings>
Common qualitative themes and their retrieval strategies:
 
| Theme | Fallback Keywords |
|-------|------------------|
| risk factors | "risk factors", "key risks", "risk profile" |
| management quality | "management team", "leadership", "executive experience" |
| corporate structure | "corporate structure", "group companies", "ownership" |
| industry position | "market position", "competitive landscape", "industry standing" |
| regulatory exposure | "regulatory risk", "compliance", "legal proceedings" |
| credit history | "credit rating", "default history", "payment record" |

</theme_mappings>
 
<workflow>
1. **Formulate comprehensive queries**: Create queries capturing the thematic elements, use multiple queries per cluster
   - Call `graph_search_facts` for trends, assessments, relationships
   - Call `graph_search_entities` for entity-specific context
        If `graph_search_entities` returns multiple entities with similar names (e.g., "Acme Corp" and "Acme Corporation Ltd"), return status `entity_ambiguous` with the list of candidates for orchestrator clarification.
   - Optionally call `vector_hybrid_search` for supporting details
3. Apply the sufficiency criteria (see `<sufficiency_criteria>` below):
    - **Sufficient**: Proceed to synthesis (Step 5).
    - **Insufficient**: Call `vector_hybrid_search` with theme-specific keywords as fallback, then re-evaluate.  Use '<theme_mappings>' as backup for keywords
2. **Multi-tool retrieval**:
4. **Synthesize**: Combine results from all tools to extract each thematic element --> summary, but keep enough detail for a wholistic view (this will be used later for report writing)
        - 3-7 sentences per specific sub-element      
5. **Structure**: Return results array with one entry per thematic element
6. **Gaps**: If a specific element is not found across all tools, mark that element as "Not available"

</workflow>
 
<sufficiency_criteria>
### When are graph results "sufficient"?
Results are **sufficient** if ALL of the following are met:
1. At least **2 distinct findings** from graph queries (entities or facts)
2. Each finding has a valid source citation (document + page)
3. Findings directly address the requested theme (not tangentially related)
 
Results are **insufficient** if ANY of the following are true:
1. Zero or one finding from graph queries
2. Findings lack source citations
3. Findings are only tangentially related to the theme
 
### Confidence mapping
| Findings Count | Source Quality | Confidence |
|----------------|----------------|------------|
| ≥ 3 findings, all with citations | High-authority documents | high |
| 2 findings, or mixed source quality | Any | medium |
| 1 finding, or required hybrid fallback | Any | low |
| 0 findings after all methods | N/A | null (status: not_found) |
</sufficiency_criteria>
 
<output_schema>
**Schema notes:**
- `status: "entity_ambiguous"`: Returned when multiple entities match the input name. Requires orchestrator to clarify.
- `entity_candidates`: List of matching entity names when ambiguous. Null otherwise.
- `clarification_question`: Suggested question to resolve ambiguity. Null if not needed.
- `status: "partial"`: Some findings retrieved but theme not fully covered (e.g., only 1 of 3 expected risk categories found).
- 'notes': Include further context of the KPI topic or explanations if you think they are useful
</output_schema>
  
<guidelines>
### Query Formulation
- For thematic clusters, formulate separate queries for each tool targeting different aspects
- For broad themes, break down into sub-queries, each focusing on a specific facet
- Examples:
    - SWOT analysis: One query for strengths, one for weaknesses, etc.
    - Risk factors: Separate queries for operational, financial, regulatory risks

### Synthesis Rules
Synthesis means **combining and rephrasing** source content, NOT interpreting or drawing conclusions.
**Allowed in summaries:**
- Restating facts from sources in your own words
- Combining multiple facts into a coherent narrative
- Using neutral descriptive language ("The company has...", "Sources indicate...")
- Listing items found in sources (e.g., "Three subsidiaries were identified: X, Y, Z")
**NOT allowed in summaries:**
- Causal inferences ("This suggests...", "This indicates risk because...")
- Evaluative judgments ("Strong management", "Weak position", "Concerning trend")
- Predictions or implications ("This could lead to...", "This may affect...")
- Comparisons not in sources ("Better than peers", "Below industry average")
 
### Entity Disambiguation
When `graph_search_entities` returns multiple entities with similar names:
1. Do NOT guess which entity the user meant
2. Return status `entity_ambiguous` with the list of candidates
3. Include a `clarification_question` for the orchestrator to relay to the user
 
### Handling Broad Themes
For broad themes like "risk_factors":
- Aim to capture multiple risk categories (operational, financial, regulatory, market)
- Set status to "partial" if only some categories are found
- Note in summary which categories were/weren't found
</guidelines>
 
<strict_boundaries>
- Always try graph queries before vector_hybrid_search fallback
- Apply sufficiency criteria before deciding to use fallback
- Do not fabricate or infer information not in sources
- Synthesis combines facts; it does NOT interpret or evaluate
- Return `entity_ambiguous` if multiple entities match — do not guess
- Return "not_found" if all retrieval methods fail
</strict_boundaries>
 
"""

class SourceDict(BaseModel):
    """Structured source information"""
    document_title: Optional[str] = Field(default=None, description="Title of the source document")
    page_number: Optional[int] = Field(default=None, description="Page number in the document")

class KPI_QUALITATIVE_OUTPUT(BaseModel):
    type: str = Field(description="entity_property or fact or narrative")
    content: str = Field(description="The qualitative content retrieved")
    source: SourceDict = Field(description="Source citation with document title and page number")

class RetrievalAgentQualitativeOutput(BaseModel):
    status: str = Field(description="Either 'found', 'partial', 'not_found', or 'entity_ambiguous'")
    query: str = Field(description="The natural language query formulated, 'original_text' from input")
    kpi_name: str = Field(description="The canonical KPI name that was asked for")
    themes: str = Field(description="Queries that were used to retrieve the thematic information")
    entity: Optional[str] = Field(default=None, description="The qualitative narrative information retrieved")
    notes: Optional[str] = Field(default=None, description="Additional notes, explanations or background about the kpi")
    summary: Optional[str] = Field(default=None, description="Concise summary of findings")
    findings: Optional[List[KPI_QUALITATIVE_OUTPUT]] = Field(default=None, description="Array of individual findings with their sources")
    confidence: Optional[str] = Field(default=None, description="Confidence level: 'high', 'medium', or 'low'")
    entity_candidates: Optional[List[str]] = Field(default=None, description="List of matching entity names when ambiguous")
    clarification_question: Optional[str] = Field(default=None, description="Suggested question to resolve ambiguity")

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
            "score": r.score
        }
        for r in results
    ]

    return results_dic


@function_tool
async def graph_search_entities(
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
        limit_entity=wrapper.context.limit_entity
    )

    results = await graph_search_tool_entities(input_data)

    # Convert result dataclass to dict for the agent
    results_dic = [
        {
            "name": r.name,
            "uuid": r.uuid,
            "summary": r.summary,
            "document_sources": r.document_sources,
            "score": r.score
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


    # Convert result dataclass to dict for the agent
    results_dic = [
        {
            "title": r.title,
            "page": r.page,
            "content": r.content,
            "score": r.score,
            "explain_score": r.explain_score,
            "table_md": r.table_md
        }
        for r in results
    ]

    return results_dic

retrieval_agent_qualitative = Agent[AgentInfo](
    name="Retrieval Agent Qualitative",
    instructions=SYSTEM_PROMPT_RETRIEVAL_AGENT_QUALITATIVE,
    output_type=AgentOutputSchema(RetrievalAgentQualitativeOutput, strict_json_schema=False),
    tools=[
        graph_search_facts,
        graph_search_entities,
        vector_hybrid_search
    ],
    model = model_gpt_5_2,
)