''' Derived KPI Agent for Multi-Agent System '''

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

from ..models import AgentInfoBasic, AgentInfo,  KPIcalcInputs, KPIcalcRes
from .retrieval_agent_quantitative import retrieval_agent_quantitative

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)

# Model IDs
model_gpt_5_2 = "gpt-5.2"
model_gpt_5mini = "gpt-5-mini"

SYSTEM_PROMPT_DERIVED_KPI_AGENT = """

<role>
You are the Derived-KPI Retriever Agent for a Credit Risk Report system. You are invoked when a direct KPI lookup fails. Your job is to retrieve the intermediate KPIs needed to compute the target KPI, then call the calculator tool.
</role>
 
<context>
You will receive from the orchestrator:
- `kpi_name`: The canonical KPI name that could not be directly retrieved
- `entity`: Company/counterparty name  
- `fiscal_year`: Target fiscal year
</context>
 
<task>
1. Look up the dependency mapping for the requested KPI
2. For each intermediate KPI: call `retrieve_kpi` tool (Quantitative Retriever as tool)
3. If all intermediates retrieved: call `kpi_calculator` with the values
4. If any intermediate fails: return "not_available" with partial results
</task>
 
<tools>
### retrieve_kpi (Quantitative Retriever Agent as tool)
Retrieve a single KPI value by delegating to the Quantitative Retriever Agent.
---
### kpi_calculator
Compute a derived KPI from intermediate values using the appropriate formula.
</tools>
 
<kpi_dependencies>
Static mapping of derived KPIs to their intermediate components:
 
| Target KPI | Intermediates Required | Formula |
|------------|----------------------|---------|
| Gross Profit | [revenue, cost_of_goods_sold] | Revenue - Cost of Goods Sold |
| Tangible Net Worth| [total_assets, intangible_assets, total_liabilities] | Total Assets - Intangible Assets - Total Liabilities |
| Total Assets | [assets_current, assets_non_current] | Current Assets + Non-current Assets |
| Total Liabilities | [liabilities_current, liabilities_non_current] | Current Liabilities + Non-current Liabilities |
| EBITA | [ebit, depreciation_amortization] | EBIT + Depreciation and Amortization |

If the target KPI is not in this mapping, return status "no_derivation_available".
</kpi_dependencies>
 

<entity_level_consistency>
### Entity Level Consistency (Group vs Standalone)
Derived KPIs must be computed from intermediate KPIs that refer to the **same reporting entity level**.

Definitions:
- **Group / Consolidated**: consolidated financial statements (e.g., "Group", "consolidated", "IFRS Group")
- **Standalone / Legal entity**: parent/company-only statements (e.g., "AG", "Company", "Standalone", "Parent")

Target level selection (default rule):
- If the input `entity` explicitly specifies a legal entity (e.g., contains "AG", "Ltd", "GmbH", "Inc." and clearly indicates standalone): use that level.
- Otherwise, default to **Group / consolidated**.

How to detect level in retrieved intermediates:
- Use explicit cues from the intermediate result's `notes`, the cited document title, or the chunk text quoted in notes.
- If the retriever explicitly states the level in `notes` (e.g., "Group" vs "AG"), trust that.
- If no cue exists: treat as **unknown** and prefer re-retrieval specifying the target level.

Consistency rule:
- Do not compute the derived KPI if intermediates are mixed across levels.
- First attempt to repair by re-calling `retrieve_kpi` for the mismatching intermediate(s), explicitly steering the query toward the target level (e.g., append "Group" to the entity context).
- Make at most **one** repair attempt per mismatching intermediate.
</entity_level_consistency>
 
<workflow>
### Step 1: Look Up Dependency Mapping
Check if the requested KPI exists in the `<kpi_dependencies>` table.
- If found: note the required intermediates and formula, proceed to Step 2.
- If not found: return status "no_derivation_available" immediately.
 
### Step 2: Retrieve Intermediate KPIs
For each intermediate KPI required:
1. Call `retrieve_kpi` tool with the intermediate KPI name, entity, and fiscal_year.
    - for intangible_assets, ensure to include "(non-current assets, balance sheet)" in the query to avoid ambiguity.
     - Apply the target entity level from `<entity_level_consistency>`:
         - If target level is Group/consolidated and `entity` does not already indicate it, include "Group" in the entity context you pass.
         - If target level is standalone/legal entity, keep the legal-entity form (e.g., "... AG").
2. Record the result including value, unit, entity, and source
3. If any intermediate returns "not_found", continue retrieving others (collect all available data)
    
### Step 3: Evaluate Retrieval Results
- **All intermediates found**: Proceed to Step 4.
- **Some intermediates missing**: Return status "partial_failure" with all retrieved values.
    - Special Case: for restricted_cash, if no value found, treat as zero (0) for calculation purposes, but note this in the output.


### Step 3b: Entity-Level Consistency Check (required before computing)
- Determine the entity level of each retrieved intermediate using `<entity_level_consistency>`.
- If any intermediate is at a different level than the target level (or differs from the majority of the other intermediates):
    - Re-call `retrieve_kpi` **once** for that intermediate with an entity context that forces the target level (e.g., append "Group" for consolidated).
    - Replace the previous value if the new retrieval matches the target level.
- If after repair attempts the intermediates are still mixed across entity levels: do not compute; return "partial_failure" and include a note describing the mismatch.
 
### Step 4: Compute Derived KPI
Call `kpi_calculator` with the intermediate numeric inputs.

#### Balance-sheet reconstruction fallback (TNW)
If the target KPI is **Tangible Net Worth** and, after Step 3b, you still observe (or strongly suspect) entity-level inconsistencies in a balance-sheet *total* intermediate (common case: totals reported for "AG" while other intermediates are "Group", or vice versa), you must reconstruct the inconsistent total(s) from their balance-sheet components at the **target entity level**.

This fallback applies to:
- **Total Assets** → reconstruct from **Current Assets** + **Non-current Assets**
- **Total Liabilities** → reconstruct from **Current Liabilities** + **Non-current Liabilities**

Procedure:
1. Identify which total(s) are inconsistent: `total_assets` and/or `total_liabilities`. Do not use the inconsistent total value(s).
2. For each inconsistent total, re-retrieve the two components at the **target entity level** (usually Group):
     - If `total_assets` inconsistent:
         - Call `retrieve_kpi` for "Current Assets" with the same entity context and fiscal_year
         - Call `retrieve_kpi` for "Non-current Assets" with the same entity context and fiscal_year
     - If `total_liabilities` inconsistent:
         - Call `retrieve_kpi` for "Current Liabilities" with the same entity context and fiscal_year
         - Call `retrieve_kpi` for "Non-current Liabilities" with the same entity context and fiscal_year
3. If both components for a total are found:
     - Pass all component values (current and non-current assets and liabilities) along with `intangible_assets` to `kpi_calculator`.
     - Record in `derived_from` that the total was reconstructed from its two components and include both citations.
4. If any required component is missing for a needed reconstruction: return "partial_failure" (do not compute TNW).
 
### Step 5: Return Result
Return structured output with computed value, formula used, and full derivation chain.
 
**Maximum tool calls:** N+1 where N = number of intermediates (N `retrieve_kpi` calls + 1 `compute_kpi` call)
</workflow>
 
<rules>
- Only attempt derivation for KPIs in the dependency mapping
- Call `retrieve_kpi` for each intermediate — do not skip any
- If any intermediate fails, report "partial_failure" with all available data
- Never estimate or fabricate intermediate values
- Enforce entity-level consistency across intermediates per `<entity_level_consistency>`; do not compute from mixed Group vs standalone values
- Permitted arithmetic (special-case only): for TNW, you may reconstruct balance-sheet totals via addition of their two components (Current + Non-current Assets, and/or Current + Non-current Liabilities) when needed; do not perform other manual computations
- If multiple candidate values are returned for the same intermediate KPI (e.g., “incl.” vs “excl.”), select one explicitly and record the selection rationale in notes. When possible, prefer the candidate whose citation matches the source document (and fiscal year) used for the other intermediate KPIs, to keep the derivation based on a consistent source.
- Do not compute ratios manually
- Output JSON only, no explanation
</rules>
"""

class DerivedKPIfromIntermediates(TypedDict):
    kpi_name: str
    value: Optional[float]
    unit: Optional[str]
    year: int
    notes: Optional[str]
    status: Literal["found", "not_found"]
    source: Optional[Dict[str, Any]]

class DerivedKPIAgentOutput(BaseModel):
    status: str = Field(description="Either 'computed', 'partial_failure', or 'no_derivation_available'")
    query: str = Field(description="The natural language query formulated, 'original_text' from input")
    kpi_name: str = Field(description="The canonical KPI name requested")
    year: int = Field(description="Fiscal Year ")
    value: Optional[float] = Field(default=None, description="The computed KPI value if derivation succeeded")
    unit: Optional[str] = Field(default=None, description="Unit of measurement for the computed KPI")
    formula_used: Optional[str] = Field(default=None, description="The formula applied for derivation")
    derived_from: List[DerivedKPIfromIntermediates] = Field(description="List of intermediate KPIs used in the derivation with their retrieval status")
    retrieval_method: Optional[str] = Field(default=None, description="'computed' or 'exhausted'")

@function_tool
async def kpi_calculator(
    target_kpi: str,
    inputs: KPIcalcInputs,
) -> KPIcalcRes:
    """
    Computes a derived KPI from intermediate values.
    
    Parameters:
        target_kpi: Canonical name of the KPI to compute
        inputs: Dictionary mapping intermediate KPI names to their numeric values
    
    Returns:
        {
            "kpi_name": str,
            "value": float,
            "formula_used": str,
            "inputs_received": Dict[str, float]
        }
    """
    def _to_scalar_number(value: Any, *, field_name: str) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)):
            total = 0.0
            for i, item in enumerate(value):
                if item is None:
                    continue
                if isinstance(item, (int, float)):
                    total += float(item)
                else:
                    raise TypeError(
                        f"{field_name} contains non-numeric value at index {i}: {type(item).__name__}"
                    )
            return total
        raise TypeError(f"{field_name} must be a number or list of numbers, got {type(value).__name__}")

    try:
        # name mapping for supported KPIs
        if target_kpi == "Gross Profit" or target_kpi == "gross_profit": target_kpi = "Gross Profit"
        if target_kpi == "Tangible Net Worth" or target_kpi == "tangible_net_worth": target_kpi = "Tangible Net Worth"
        if target_kpi == "Unrestricted Cash" or target_kpi == "unrestricted_cash": target_kpi = "Unrestricted Cash"
        if target_kpi == "EBITDA" or target_kpi == "Earnings Before Interest, Taxes, Depreciation and Amortization" or target_kpi == "ebita": target_kpi = "EBITDA"

        if target_kpi == "Gross Profit":
            revenue = _to_scalar_number(inputs.get("revenue"), field_name="revenue")
            cogs = _to_scalar_number(inputs.get("cogs"), field_name="cogs")
            if revenue is None or cogs is None:
                raise ValueError("Missing inputs for gross profit calculation")
            gross_profit = revenue - cogs
            return {
                "kpi_name": "gross_profit",
                "value": gross_profit,
                "formula_used": "gross_profit = revenue - cogs",
                "inputs_received": {"revenue": revenue, "cogs": cogs}
            }
        elif target_kpi == "Tangible Net Worth":
            total_assets_raw = inputs.get("total_assets")
            if total_assets_raw is None:
                current_assets = inputs.get("assets_current")
                non_current_assets = inputs.get("assets_non_current")
                if current_assets is None or non_current_assets is None:
                    raise ValueError("Missing inputs for total assets reconstruction")
                total_assets = (_to_scalar_number(current_assets, field_name="assets_current") or 0.0) + (
                    _to_scalar_number(non_current_assets, field_name="assets_non_current") or 0.0
                )
            else:
                total_assets = _to_scalar_number(total_assets_raw, field_name="total_assets")

            total_liabilities_raw = inputs.get("total_liabilities")
            if total_liabilities_raw is None:
                current_liabilities = inputs.get("liabilities_current")
                non_current_liabilities = inputs.get("liabilities_non_current")

                if current_liabilities is None or non_current_liabilities is None:
                    raise ValueError("Missing inputs for total liabilities reconstruction")
                total_liabilities = (_to_scalar_number(current_liabilities, field_name="liabilities_current") or 0.0) + (
                    _to_scalar_number(non_current_liabilities, field_name="liabilities_non_current") or 0.0
                )
            else:
                total_liabilities = _to_scalar_number(total_liabilities_raw, field_name="total_liabilities")

            intangible_assets = _to_scalar_number(inputs.get("intangible_assets"), field_name="intangible_assets")
            if total_assets is None or total_liabilities is None or intangible_assets is None:
                raise ValueError("Missing inputs for tangible net worth calculation")
            tangible_net_worth = total_assets - total_liabilities - intangible_assets
            return {
                "kpi_name": "tangible_net_worth",
                "value": tangible_net_worth,
                "formula_used": "tangible_net_worth = total_assets - total_liabilities - intangible_assets",
                "inputs_received": {
                    "total_assets": total_assets,
                    "total_liabilities": total_liabilities,
                    "intangible_assets": intangible_assets
                }
            }
        elif target_kpi == "Unrestricted Cash":
            total_cash = _to_scalar_number(inputs.get("total_cash"), field_name="total_cash")
            restricted_cash = _to_scalar_number(inputs.get("restricted_cash"), field_name="restricted_cash") or 0.0
            if total_cash is None:
                raise ValueError("Missing inputs for unrestricted cash calculation")
            unrestricted_cash = total_cash - restricted_cash
            return {
                "kpi_name": "unrestricted_cash",
                "value": unrestricted_cash,
                "formula_used": "unrestricted_cash = total_cash - restricted_cash",
                "inputs_received": {
                    "total_cash": total_cash,
                    "restricted_cash": restricted_cash
                }
            }
        elif target_kpi == "EBITDA":
            ebit = _to_scalar_number(inputs.get("ebit"), field_name="ebit")
            depreciation_amortization = _to_scalar_number(
                inputs.get("depreciation_amortization"),
                field_name="depreciation_amortization",
            )
            if ebit is None or depreciation_amortization is None:
                raise ValueError("Missing inputs for EBITA calculation")
            ebita = ebit + depreciation_amortization
            return {
                "kpi_name": "ebita",
                "value": ebita,
                "formula_used": "ebita = ebit + depreciation_amortization",
                "inputs_received": {"ebit": ebit, "depreciation_amortization": depreciation_amortization},
            }
        else:
            raise ValueError(f"Unsupported target KPI: {target_kpi}")

    except Exception as e:
        return {
            "kpi_name": str(target_kpi),
            "value": None,
            "formula_used": "",
            "inputs_received": {},
            "error": str(e),
        }

# Define the Derived KPI Agent
derived_kpi_agent = Agent[AgentInfo](
    name="derived_kpi_agent",
    instructions=SYSTEM_PROMPT_DERIVED_KPI_AGENT,
    output_type=AgentOutputSchema(DerivedKPIAgentOutput, strict_json_schema=False),
    tools=[kpi_calculator, retrieval_agent_quantitative.as_tool(tool_name="retrieve_kpi", tool_description="Retrieve quantitative KPI values for calculation.")],
    model = model_gpt_5_2,
)