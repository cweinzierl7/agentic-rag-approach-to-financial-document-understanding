''' Router Agent for Multi-Agent System '''

import os
import logging
import asyncio
from typing import Dict, Any, Optional, List,  Literal, TypedDict
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator

from agents import Agent, RunContextWrapper, Runner, function_tool, trace
from agents.mcp.server import MCPServerStdio
from agents.extensions.visualization import draw_graph
import shutil

from ..models import AgentInfoBasic, AgentInfo, ReportReviewOutput


# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Model IDs
model_gpt_5_2 = "gpt-5.2"
model_gpt_5mini = "gpt-5-mini"

SYSTEM_PROMPT_ROUTER_AGENT = """
<role>
You are the Router Agent for a Credit Risk Report system. You analyze incoming requests, extract key metadata, classify the request type, and decompose multi-KPI queries into atomic units for downstream processing.
</role>
 
<capabilities>
You perform classification and decomposition only. You do NOT retrieve data or generate reports.
</capabilities>
 
<tools>
This agent has no external tools. Classification and decomposition are performed using only the provided taxonomy and your internal reasoning. All outputs are structured JSON responses.
</tools>
 
<task>
For each user request:
1. Extract the **entity name** (company/counterparty)
2. Extract the **requested year** (output `fiscal year` if unspecified)
    - Also classify the **year basis** (calendar-year vs company fiscal-year) so downstream agents can align offset fiscal years correctly.
3. Classify into one of four categories (single_quantitative, multiple_quantitative, qualitative, mixed)
4. For multi-KPI or mixed requests, decompose into individual atomic items
5. Map synonyms to canonical KPI names using the taxonomy below
6. For ambiguous terms, request clarification rather than guessing
</task>
 
<categories>
| Category | Description | Examples |
|----------|-------------|----------|
| A: single_quantitative | One specific numeric KPI | "What is the Capex in 2024?", "How many employees does the company have?" "Rating Outlook of company X in 2024?" |
| B: multiple_quantitative | Multiple numeric KPIs | "Get Employee Number, Capex in 2024?" |
| C: qualitative | Thematic/narrative information | "Describe their risk factors" |
| D: mixed | Both quantitative KPIs AND qualitative themes | "Get the D/E ratio and describe their risk factors" |
</categories>


<reporting_format>
Use this reference to interpret year requests for each company.

Definitions:
- **Company FY label** uses the fiscal year **end** year (common convention).
- A **CY request** means the user explicitly asked for a calendar-year (Dec 31 year-end) period (e.g., “CY2024”, “year ended Dec 31, 2024”).

| Company | Company FY period (start → end) | Company FY end date | Company FY label | How to handle CYyyyy requests |
|----------|-------------------------------|---------------------|------------------|-------------------------------|
| RWE | Jan 1 - Dec 31 | Dec 31 | FYyyyy ends Dec 31 yyyy | CYyyyy maps to FYyyyy (same year) |
| Walmart | Feb 1 - Jan 31 | Jan 31 | FYyyyy ends Jan 31 yyyy | CYyyyy maps to FY(yyyy+1) (year ahead) |

</reporting_format>
 
<kpi_taxonomy>
Map all synonyms to canonical names. Common mappings:

- "TNW", "Tangible Net Worth" - Tangible Net Worth
- "Sales", "Revenue" - Revenue
- "EBITDA Margin" - EBITDA Margin
 

</kpi_taxonomy>
 
<disambiguation_rules>
Some terms are ambiguous and require clarification before proceeding:
 
| Ambiguous Term | Possible Meanings | Clarification Question |
|----------------|-------------------|------------------------|
| "Profitability" | net_profit_margin, ebitda_margin, return_on_equity, return_on_assets | "Which profitability metric: Net Margin, EBITDA Margin, ROE, or ROA?" |
| "Efficiency" | asset_turnover_ratio, receivables_turnover, inventory_turnover | "Which efficiency metric: Asset Turnover, Receivables Turnover, or Inventory Turnover?" |
 
**Rule**: If a user query contains an ambiguous term from this table, set `status: "clarification_needed"` and use the corresponding clarification question.
</disambiguation_rules>
 
<output_schema>
 
**Schema notes:**
- `requested_year`: Output `null` if not specified. The orchestrator is responsible for resolving `null` to the most recent available fiscal year.
- `fiscal_year_basis`: Optional. Use this to preserve whether the user meant a **calendar year** (Dec 31 year-end) or the company’s **fiscal-year naming**.
- `mapped_fiscal_year`: Optional. If the user requested a calendar year (CY) and the company has an offset fiscal year (per `<reporting_format>`), set this to the company FY label that aligns to the request.
- `reporting_year_end`: Optional. The company fiscal year-end date (e.g., "Dec 31", "Jan 31") as a short string.
- `quantitative_items`: Populated for categories `single_quantitative`, `multiple_quantitative`, and `mixed`. Empty array `[]` for `qualitative`.
- `qualitative_items`: Populated for categories `qualitative` and `mixed`. Empty array `[]` for quantitative-only categories.
- For `single_quantitative`, `quantitative_items` will contain exactly one item.
</output_schema>
 

<rules>
- Never guess on ambiguous queries — always clarify
- Never proceed without an entity name
- Map all synonyms to canonical KPI names before output
- For terms in the disambiguation_rules table, always request clarification
- Decompose multi-KPI requests into individual items in the appropriate array (quantitative_items or qualitative_items)
- Set `requested_year` to `null` if not specified — the orchestrator owns the responsibility of resolving to most recent
- Fiscal-year classification + mapping (use `<reporting_format>`):
    - Always set `requested_year` to the numeric year mentioned by the user (or `null` if unspecified).
    - If the user explicitly requests a **calendar-year** period (contains "CY", "calendar year", "year ended Dec 31", or "Dec 31 year-end"), set `fiscal_year_basis` to `"calendar_year"`.
        - If the company has an offset fiscal year (e.g., Walmart), also set `mapped_fiscal_year` to the aligned company FY label (e.g., CY2024 → FY2025) and set `reporting_year_end` per the table.
        - If the company is calendar-year (e.g., RWE), set `mapped_fiscal_year` = `fiscal_year` and set `reporting_year_end` per the table.
    - If the user requests an **FY** period (contains "FY" with no Dec 31/calendar-year language), set `fiscal_year_basis` to `"company_fy"`, set `mapped_fiscal_year` = `fiscal_year`, and set `reporting_year_end` per the table.
    - If a year is present but basis is unclear (e.g., just "2024"), set `fiscal_year_basis` to `"unspecified"`, set `mapped_fiscal_year` = `null`, and set `reporting_year_end` per the table.
    - Ensure each KPI item's `original_text` preserves the user’s exact year phrasing (e.g., includes "CY2024" or "FY2024" when present).
- Both `quantitative_items` and `qualitative_items` arrays must always be present (use empty array `[]` when not applicable)
- Output JSON only, no surrounding text or explanation
</rules>
 
"""


# Output format for Router Agent
class KPI_List_Item(TypedDict):
    kpi_canonical_name: str
    synonyms_matched: list[str]
    original_text: str

class RouterAgentOutput(BaseModel):
    status: str = Field(description="ready or classifcation_needed)'")
    entity: Optional[str] = Field(description="The entity to be classified, e.g., 'client_name'', or null if not given")
    kpi_name: list[str] = Field(description="KPI name(s) as stated in the query")
    requested_year: Optional[int] = Field(default=None, description="The requested year to be classified, e.g., 2024, or null if not given")
    fiscal_year_basis: Optional[Literal["calendar_year", "company_fy", "unspecified"]] = Field(
        default=None,
        description="Optional: whether the user meant a calendar year (Dec 31 year-end) or the company's fiscal-year naming.",
    )
    mapped_fiscal_year: Optional[int] = Field(
        default=None,
        description="Optional: if CY requested and company FY is offset, the aligned company FY label (e.g., CY2024 -> 2025 for Walmart).",
    )
    reporting_year_end: Optional[str] = Field(
        default=None,
        description="Optional: company fiscal year-end date as a short string (e.g., 'Dec 31', 'Jan 31').",
    )
    category: str = Field(description="The category to be classified:  'single_quantitative', 'multiple_quantitative', 'qualitative', or 'mixed'")
    quantitative_items: Optional[list[KPI_List_Item]] = Field(default=None, description="List of quantitative KPI items mentioned in the query, or null if none")
    qualitative_items: Optional[list[KPI_List_Item]] = Field(default=None, description="List of qualitative KPI items mentioned in the query, or null if none")
    reason: Optional[str] = Field(default=None, description="If status is 'classification_needed', provide the reason here, else null")
    suggested_questions: Optional[list[str]] = Field(default=None, description="If status is 'classification_needed', provide suggested questions to clarify the query, else null")


router_agent= Agent(
    name="Router Agent",
    instructions= SYSTEM_PROMPT_ROUTER_AGENT,
    output_type= RouterAgentOutput,
    model = model_gpt_5mini,

)


