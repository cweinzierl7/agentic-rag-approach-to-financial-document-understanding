"""
Single agent for agentic RAG 
"""



import os
import logging
import asyncio
from typing import Dict, Any, Optional, TypedDict, List
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import json
import ast


from agents import Agent, RunContextWrapper, Runner, function_tool, trace, ModelSettings
from agents.mcp.server import MCPServerStdio
from agents.extensions.visualization import draw_graph
import shutil

from ..tools import graph_search_tool_facts, graph_search_tool_entities, vector_hybrid_search_tool, vector_search_tool  # Assuming your tool is defined here
from ..graph_utils import initialize_graph, test_graph_connection, close_graph
from ..vector_db_utils import initialize_database, close_database
from .prompt_single_agent import SYSTEM_PROMPT_SINGLE_PATTERNS_FINAL
from ..query_qualtitative_kpi import  QualitativeKPIs_speedboat
from ..query_quantitative_kpi import QUANTITATIVE_KPIs_speedboat
from ..tools import GraphSearchInput, HybridSearchInput, VectorSearchInput
from ..models import AgentInfo, KPI_Output, SourceDict, KPIcalcInputs, KPIcalcRes
import os
from datetime import datetime

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================================
#   CONFIGURATION REMINDER
# ============================================================================
# Before running, set the following parameters in the main() function
# (around line 1260):
#
#   1. company           Target company name 
#   2. agent_info        Retrieval parameters:
#                        - reranker_entity, reranker_fact (e.g., "RRF")
#                        - limit_vector_results, limit_fact, limit_entity
#                        - alpha_hybrid (semantic vs keyword weight)
#                        - k (sentence window retrieval parameter)
#   3. year_basis        OPTIONAL: Fiscal year basis (e.g., "FY")
#   4. year_0/1/2        Fiscal years for quantitative KPI queries
#
# See main() function starting around line 1260 for details.
# ============================================================================


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

    def _unwrap_scalar(value: Any) -> Any:
        """Normalize values that may arrive as single-element tuples/lists."""
        if isinstance(value, (list, tuple)):
            return value[0] if value else value
        return value

    input_data = GraphSearchInput(
        query=query,
        reranker_entity=_unwrap_scalar(wrapper.context.reranker_entity),
        reranker_fact=_unwrap_scalar(wrapper.context.reranker_fact),
        group_id=_unwrap_scalar(wrapper.context.client),
        limit_fact=_unwrap_scalar(wrapper.context.limit_fact)
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

    def _unwrap_scalar(value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return value[0] if value else value
        return value

    input_data = GraphSearchInput(
        query=query,
        reranker_entity=_unwrap_scalar(wrapper.context.reranker_entity),
        reranker_fact=_unwrap_scalar(wrapper.context.reranker_fact),
        group_id=_unwrap_scalar(wrapper.context.client),
        limit_entity=_unwrap_scalar(wrapper.context.limit_entity)
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


@function_tool
async def vector_search(
    wrapper: RunContextWrapper[AgentInfo],
    query: str,

) -> Dict[str, Any]:
    """
    Perform a vector search using the provided query.

    Args:
        query: The search query string.
        wrapper: Context wrapper containing AgentInfo.

    Returns:
        A dictionary containing the search results.
    """
    logger.info(f"Performing vector search for query: {query}")

    input_data = VectorSearchInput(
        query=query,
        limit=wrapper.context.limit_vector_results,
        client=wrapper.context.client,
        k = wrapper.context.k
    )

    results = await vector_search_tool(input_data)


    # Convert result dataclass to dict for the agent
    results_dic = [
        {
            "title": r.title,
            "page": r.page,
            "content": r.content,
           # "score": r.score,
            "table_md": r.table_md,
            #"distance": r.distance,
        }
        for r in results
    ]

    return results_dic




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


def format_kpis_markdown(kpi_results: list[dict]) -> str:
    """
    Takes a list of KPI result dictionaries and returns Markdown formatted text.
    KPI and Value are always printed. Response is included only for qualitative items.
    """
    lines = []
    for item in kpi_results:
        kpi = item.get("kpi", "")
        notes = item.get("notes", "")
        source = item.get("source", "")
        resp_section = ""
        if item.get("type") == "qualitative":
            resp_section = f"**Response:** {item.get('response', '')}\n\n"
        if item.get("type") == "quantitative":
            resp_section = f"**Value:** {item.get('value', '')}\n\n"

        lines.append(
            f"### {kpi}\n"
            f"{resp_section}"
            f"**Notes:** {notes}\n\n"
            f"**Source:** {source}\n"
        )
    return "\n---\n".join(lines)


def make_markdown_table(kpi_blocks):
    """
    Converts a list of KPI blocks into a markdown table.
    
    Each element in kpi_blocks is expected to be a dict like:
    {
      "kpi": "...",
      "year": "...",
      "response": "...",  # OR "value": "...",
      "notes": "...",
      "source": "..."
    }
    """

    # Table header
    md = [
        "| KPI | Year | Value/Response | Notes | Source |",
        "|-----|------|----------------|-------|--------|"
    ]

    def _safe_cell(v: Any) -> str:
        if v is None:
            return ""
        s = str(v)
        # replace newlines with <br> so table cell remains one line
        s = s.replace("\r\n", "\n").replace("\n", "<br>")
        # escape pipes that would break the markdown table
        s = s.replace("|", "\\|")
        return s.strip()

    def _format_sources(raw_sources: Any) -> str:
        if raw_sources is None or raw_sources == "":
            return ""

        if isinstance(raw_sources, str):
            return _safe_cell(raw_sources)

        if isinstance(raw_sources, dict):
            raw_sources = [raw_sources]

        if not isinstance(raw_sources, list):
            return _safe_cell(raw_sources)

        parts: list[str] = []
        for src in raw_sources:
            if not isinstance(src, dict):
                parts.append(_safe_cell(src))
                continue

            document = src.get("document") or src.get("title") or ""
            pages = src.get("page") or src.get("pages")
            if isinstance(pages, list):
                pages_str = ", ".join(str(p) for p in pages)
            elif pages is None:
                pages_str = ""
            else:
                pages_str = str(pages)

            if document and pages_str:
                parts.append(f"{document}, page(s) {pages_str}")
            elif document:
                parts.append(document)
            elif pages_str:
                parts.append(f"page(s) {pages_str}")

        return _safe_cell("; ".join(p for p in parts if p))

    for block in kpi_blocks:
        kpi = _safe_cell(block.get("kpi", ""))
        year = _safe_cell(block.get("year", ""))
        value = _safe_cell(block.get("value") or block.get("response") or "")
        notes = _safe_cell(block.get("notes", ""))
        source_str = _format_sources(block.get("source"))

        md.append(f"| **{kpi}** | {year} | {value} | {notes} | {source_str} |")

    return "\n".join(md)


def make_kpi_attribute_string(kpi_blocks: List[Dict[str, Any]]) -> str:
    parts: List[str] = []

    def _one_line(text: str) -> str:
        # Collapse any whitespace (including newlines) into single spaces.
        return " ".join(text.split()).strip()

    def _safe(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, str):
            return _one_line(v)
        return _one_line(str(v))

    def _format_sources(raw_sources: Any) -> str:
        if raw_sources is None or raw_sources == "":
            return ""

        if isinstance(raw_sources, str):
            return _one_line(raw_sources)

        if isinstance(raw_sources, dict):
            raw_sources = [raw_sources]

        if not isinstance(raw_sources, list):
            return _one_line(str(raw_sources))

        formatted: List[str] = []
        for src in raw_sources:
            if not isinstance(src, dict):
                formatted.append(_safe(src))
                continue
            document = src.get("document") or src.get("title") or ""
            pages = src.get("page") or src.get("pages")
            if isinstance(pages, list):
                pages_str = ", ".join(str(p) for p in pages)
            elif pages is None:
                pages_str = ""
            else:
                pages_str = str(pages)

            if document and pages_str:
                formatted.append(f"{document}, page(s) {pages_str}")
            elif document:
                formatted.append(document)
            elif pages_str:
                formatted.append(f"page(s) {pages_str}")

        return _one_line("; ".join(s for s in (f.strip() for f in formatted) if s))

    for block in kpi_blocks:
        if not isinstance(block, dict):
            parts.append(_safe(block))
            continue

        kpi = _safe(block.get("kpi", ""))
        year = _safe(block.get("year", ""))
        value = _safe(block.get("value"))
        response = _safe(block.get("response"))
        notes = _safe(block.get("notes", ""))
        source = _format_sources(block.get("source"))

        value_or_response = value or response

        fields: List[str] = []
        if kpi:
            fields.append(f"KPI: {kpi}")
        if year:
            fields.append(f"Year: {year}")
        if value_or_response:
            label = "Value" if value else "Response"
            fields.append(f"{label}: {value_or_response}")
        if notes:
            fields.append(f"Notes: {notes}")
        if source:
            fields.append(f"Source: {source}")

        parts.append(_one_line(" | ".join(fields)))

    # Join multiple KPI blocks in a single line as well.
    return _one_line(" || ".join(p for p in (p.strip() for p in parts) if p))


# Model IDs
model_gpt_5_2 = "gpt-5.2"
model_gpt_5mini = "gpt-5-mini"

# Define the agent
single_agent = Agent[AgentInfo](
    name="Single Agentic RAG",
    instructions=SYSTEM_PROMPT_SINGLE_PATTERNS_FINAL,
    tools=[vector_hybrid_search, graph_search_facts, graph_search_entities, kpi_calculator],
    model=model_gpt_5_2,
    output_type=KPI_Output,
)
#draw_graph(single_agent).view()

# class single-agent_run used for single query execution for evaluation
class single_agent_run: 

    def __init__(self, client: str = "default_client", 
                reranker_entity: str = "RRF", 
                reranker_fact: str = "RRF", 
                limit_vector_results: int = 15,
                alpha_hybrid: float = 0.7,
                limit_fact: int = 30,
                limit_entity: int = 10,
                k: int = 2          
                ) -> None:
        def _unwrap_scalar(value: Any) -> Any:
            if isinstance(value, (list, tuple)):
                return value[0] if value else value
            return value

        self.client = _unwrap_scalar(client)
        self.reranker_entity = _unwrap_scalar(reranker_entity)
        self.reranker_fact = _unwrap_scalar(reranker_fact)
        self.limit_vector_results = _unwrap_scalar(limit_vector_results)
        self.alpha_hybrid = _unwrap_scalar(alpha_hybrid)
        self.limit_fact = _unwrap_scalar(limit_fact)
        self.limit_entity = _unwrap_scalar(limit_entity)
        self.k = _unwrap_scalar(k)
    
    async def run_eval(self, query_list: list[str], kpi_name_expected: Optional[list[str]] = None) -> Any:
        agent_info = AgentInfo(
            client=self.client,
            reranker_entity=self.reranker_entity,
            reranker_fact=self.reranker_fact,
            limit_vector_results=self.limit_vector_results,
            alpha_hybrid=self.alpha_hybrid,
            limit_fact=self.limit_fact,
            limit_entity=self.limit_entity,
            k = self.k,
            
        )

        
        response_user = ""
        response_user_list = []
        final_output = None  # Initialize to handle errors
        retrieved_contexts_list = []  # Track contexts across queries

        if self.client =="default_client": company = "RWE"
        else: company = self.client
        try: 
            with trace(f"Single A. Eval {company} {kpi_name_expected}"):
                for q in query_list:
                        response = await Runner.run(
                        single_agent,
                        input= q,
                        context=agent_info,
                        )
                        # if using structured output
                        fo = response.final_output
                        if fo is None:
                            fo_dict = {}
                        else:
                            try:
                                fo_dict = fo.model_dump()
                            except Exception as model_err:
                                logger.warning(f"Could not dump model: {model_err}, using dict conversion")
                                fo_dict = fo.__dict__ if hasattr(fo, '__dict__') else {}
                        response_user_list.append(fo_dict)

                        # now use your formatter
                        # format_kpis_markdown expects a list of dicts.
                        if not fo_dict:
                            # nothing to append
                            continue
                        to_format = fo_dict if isinstance(fo_dict, list) else [fo_dict]
                        response_user += "\n" + format_kpis_markdown(to_format)
        
                answer = make_kpi_attribute_string(response_user_list)
                

                # create outputs folder inside the agent package directory
                timestamp_folder = datetime.now().strftime("%Y%m%d_%H")

                agent_dir = os.path.dirname(__file__)
                outputs_dir = os.path.join(agent_dir, f"outputs_single_agent/eval/{timestamp_folder}")
                os.makedirs(outputs_dir, exist_ok=True)

                # build filename with date and time
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                kpi_for_filename = (
                    getattr(response.final_output, "kpi", None)
                    if getattr(response, "final_output", None) is not None
                    else None
                )
                if not kpi_for_filename:
                    kpi_for_filename = fo_dict.get("kpi", "unknown") if isinstance(fo_dict, dict) else "unknown"
                filename = f"{self.client}_{kpi_for_filename}_single_eval_alpha{self.alpha_hybrid}_vector_{self.limit_vector_results}_k{self.k}_entity{self.limit_entity}_fact{self.limit_fact}_{timestamp}_.md"
                filepath = os.path.join(outputs_dir, filename)

                # write final response to markdown file
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(answer)
                    logger.info(f"Final response saved to {filepath}")
                except Exception as e:
                    logger.error(f"Failed to save final response: {e}")
                

                if len(query_list) == 1: query = query_list[0]
                else: raise ValueError("Query list must contain exactly one query for single_agent_run.")
                
                    
                # Extract contexts from response.all_messages
                # retrieved_contexts_list = self._extract_contexts_from_response(response)
                # print("Retrieved Contexts:\n", retrieved_contexts_list)
                retrieved_contexts_list = self._prepare_context(response.to_input_list())
                #print("context", retrieved_contexts_list)
                intermediate_output = {
                    "query": query,
                    "answer": answer,
                    "contexts": retrieved_contexts_list,
                    "sources": fo_dict.get("source", "")
                }
            final_output = {
                "kpi_name": response.final_output.kpi if response.final_output else "",
                "year": response.final_output.year if response.final_output else "",
                "query": intermediate_output["query"],
                "answer": intermediate_output["answer"],
                "contexts": intermediate_output["contexts"],
                "sources": intermediate_output.get("sources", "")
            }       

        except Exception as e:
            logger.error(f"Error during agent run: {e}", exc_info=True)
            query = query_list[0] if query_list else "unknown"
            final_output = {
                "query": query,
                "answer": f"Error: {str(e)}",
                "contexts": []
            }

        return final_output
    
    def _extract_contexts_from_response(self, response) -> List[str]:
        """Extract retrieved contexts from agent response messages."""
        contexts = []
        try:
            # Access all messages in the response
            if hasattr(response, 'all_messages'):
                for msg in response.all_messages:
                    # Look for tool call results with context data
                    if hasattr(msg, 'role') and msg.role == 'tool':
                        if hasattr(msg, 'content'):
                            content = msg.content
                            # Try to parse if it's JSON string
                            if isinstance(content, str):
                                try:
                                    data = json.loads(content)
                                    contexts.extend(self._extract_text_from_data(data))
                                except (json.JSONDecodeError, TypeError):
                                    pass
                            elif isinstance(content, list):
                                contexts.extend(self._extract_text_from_data(content))
                            elif isinstance(content, dict):
                                contexts.extend(self._extract_text_from_data(content))
        except Exception as e:
            logger.warning(f"Error extracting contexts from response: {e}")
        
        return contexts
    
    def _extract_text_from_data(self, data) -> List[str]:
        """Recursively extract text summaries/facts from data structures."""
        texts = []
        
        if isinstance(data, list):
            for item in data:
                texts.extend(self._extract_text_from_data(item))
        elif isinstance(data, dict):
            # Priority: summary > fact > content > table_md
            if "summary" in data:
                summary = data.get("summary", "")
                doc_src = data.get("document_sources", "")
                if summary:
                    texts.append(f"{summary} (Source: {doc_src})" if doc_src else summary)
            elif "fact" in data:
                fact = data.get("fact", "")
                doc_src = data.get("document_sources", "")
                if fact:
                    texts.append(f"{fact} (Source: {doc_src})" if doc_src else fact)
            elif "content" in data:
                content = data.get("content", "")
                if content:
                    texts.append(content)
            elif "table_md" in data:
                table = data.get("table_md", "")
                if table:
                    texts.append(table)
        
        return texts
    def _prepare_context(self, result: List[Dict[str, Any]], agent_tool: str = "Tool") -> List[str]:
        outputs = []
        tool_name = None

        if agent_tool == "Tool": 
            for i, ctx in enumerate(result):
                output = ctx.get("output") if "output" in ctx else None
                parsed_output = None
                if isinstance(output, str):
                    try:
                        parsed_output = json.loads(output)
                    except Exception:
                        try:
                            parsed_output = ast.literal_eval(output)
                        except Exception:
                            parsed_output = None
                parsed_output = {"data": parsed_output}
                
                if parsed_output["data"] is not None:
                    outputs.append(parsed_output)
                    
        elif agent_tool == "Agent":
            content_items = result[-1].get("content") if "content" in result[-1] else None
            if content_items:
                for item in content_items:                
                    if "text" in item:  # Now properly inside the loop
                        text_content = item.get("text")
                        parsed_output = None
                        
                        if isinstance(text_content, str):
                            try:
                                parsed_output = json.loads(text_content)
                            except Exception as e:
                                print(f"JSON parsing failed: {e}")
                                try:
                                    parsed_output = ast.literal_eval(text_content)
                                    print("Parsed output via ast:", parsed_output)
                                except Exception as e2:
                                    print(f"AST parsing failed: {e2}")
                                    parsed_output = None
                        
                        if parsed_output is not None:
                            outputs.append({"data": parsed_output})

        context_list = []
        for entry in outputs:
            data = entry.get("data")
            if data is None:
                continue
                
            # Handle if data is a list
            if isinstance(data, list):
                entities = data
            # Handle if data is a dict with nested structure
            elif isinstance(data, dict):
                entities = [data]
            else:
                continue
                
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                    
                if "summary" in entity:
                    # Entity retrieval context
                    context = entity.get("summary", "")
                    doc_src = entity.get("document_sources", "")
                    context_list.append(f"{context} ---- {doc_src}".strip())
                elif "fact" in entity:
                    # Fact retrieval context
                    fact = entity.get("fact", "")
                    doc_src = entity.get("document_sources", "")
                    context_list.append(f"{fact} ---- {doc_src}".strip())
                elif "table_md" in entity:
                    # Vector DB retrieval context
                    chunk = entity.get("content", "")
                    table = entity.get("table_md", "")
                    doc_src = entity.get("title", "")
                    doc_page = entity.get("page", "")
                    context_list.append(f"{chunk} {table} ---- {doc_src}, page {doc_page}".strip())
                elif "formula_used" in entity:
                    # KPI calculation context
                    kpi_name = entity.get("kpi_name", "")
                    formula = entity.get("formula_used", "")
                    inputs_received = entity.get("inputs_received", "")
                    context_list.append(f"KPI {kpi_name} calculated via formula: {formula} with inputs {inputs_received}".strip())   
                elif "category" in entity:
                    # Router decision context
                    category = entity.get("category", "")
                    entity_name = entity.get("entity", "")
                    fiscal_year = entity.get("fiscal_year", "")
                    qualitative_items = entity.get("qualitative_items", "")
                    quantitative_items = entity.get("quantitative_items", "")
                    context_list.append(f"Router decision: category {category} for entity {entity_name} in fiscal year {fiscal_year} with qualitative items {qualitative_items} and quantitative items {quantitative_items}".strip())
        
        return context_list


# class single_agent_run_input_list returns the full conversation history including tool calls
class single_agent_run_input_list:
    """
    Similar to single_agent_run but returns the complete conversation history
    including all agent messages, tool inputs, tool outputs, etc.
    """

    def __init__(self, client: str = "default_client", 
                reranker_entity: str = "RRF", 
                reranker_fact: str = "RRF", 
                limit_vector_results: int = 15,
                alpha_hybrid: float = 0.7,
                limit_fact: int = 30,
                limit_entity: int = 10,
                k: int = 2          
                ) -> None:
        def _unwrap_scalar(value: Any) -> Any:
            if isinstance(value, (list, tuple)):
                return value[0] if value else value
            return value

        self.client = _unwrap_scalar(client)
        self.reranker_entity = _unwrap_scalar(reranker_entity)
        self.reranker_fact = _unwrap_scalar(reranker_fact)
        self.limit_vector_results = _unwrap_scalar(limit_vector_results)
        self.alpha_hybrid = _unwrap_scalar(alpha_hybrid)
        self.limit_fact = _unwrap_scalar(limit_fact)
        self.limit_entity = _unwrap_scalar(limit_entity)
        self.k = _unwrap_scalar(k)
    
    async def run_with_full_history(self, query_list: list[str], kpi_name: Optional[str]="") -> Dict[str, Any]:
        """
        Run the agent and return the full conversation history.
        
        Returns:
            Dict containing:
                - query: The original query
                - final_output: The structured KPI output
                - input_list: Full conversation history from to_input_list()
                - all_messages: Raw messages from the agent run
                - tool_calls: Extracted tool call details (name, input, output)
                - contexts: Extracted context strings
        """
        agent_info = AgentInfo(
            client=self.client,
            reranker_entity=self.reranker_entity,
            reranker_fact=self.reranker_fact,
            limit_vector_results=self.limit_vector_results,
            alpha_hybrid=self.alpha_hybrid,
            limit_fact=self.limit_fact,
            limit_entity=self.limit_entity,
            k=self.k
        )
        if self.client == "default_client": company = "RWE"
        else: company = self.client
        try:
            with trace(f"{company} {kpi_name} Single Agent"):
                for q in query_list:
                    response = await Runner.run(
                        single_agent,
                        input=q,
                        context=agent_info,
                    )
                    
                    # Get structured output
                    fo = response.final_output
                    if fo is None:
                        fo_dict = {}
                    else:
                        try:
                            fo_dict = fo.model_dump()
                        except Exception:
                            fo_dict = fo.__dict__ if hasattr(fo, '__dict__') else {}
                    
                    # Get the full input list (conversation history)
                    input_list = response.to_input_list()
                    
                    # Extract tool calls with their inputs and outputs
                    tool_calls = self._extract_tool_calls(input_list)
                    
                    # Extract contexts (reusing existing method logic)
                    contexts = self._prepare_context(input_list)
                    
                    if len(query_list) == 1:
                        query = query_list[0]
                    else:
                        query = query_list

                    return {
                        "query": query,
                        "final_output": fo_dict,
                        "input_list": input_list,
                        "tool_calls": tool_calls,
                        "contexts": contexts,
                        "kpi_name": fo_dict.get("kpi", "") if fo_dict else "",
                        "year": fo_dict.get("year", "") if fo_dict else "",
                    }

        except Exception as e:
            logger.error(f"Error during agent run: {e}", exc_info=True)
            query = query_list[0] if query_list else "unknown"
            return {
                "query": query,
                "final_output": {},
                "input_list": [],
                "tool_calls": [],
                "contexts": [],
                "error": str(e)
            }

    def _extract_tool_calls(self, input_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract tool call information from the input list.
        
        Returns a list of dicts with:
            - tool_name: Name of the tool called
            - tool_input: Input arguments to the tool
            - tool_output: Output from the tool
            - call_id: The tool call ID
        """
        tool_calls = []
        
        # Build a map of call_id -> output
        output_map = {}
        for item in input_list:
            if item.get("type") == "function_call_output":
                call_id = item.get("call_id")
                output = item.get("output")
                if call_id:
                    output_map[call_id] = output
        
        # Now extract tool calls with their inputs
        for item in input_list:
            if item.get("type") == "function_call":
                call_id = item.get("call_id")
                tool_name = item.get("name")
                arguments = item.get("arguments")
                
                # Parse arguments if string
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except Exception:
                        pass
                
                # Get corresponding output
                output = output_map.get(call_id)
                if isinstance(output, str):
                    try:
                        output = json.loads(output)
                    except Exception:
                        pass
                
                tool_calls.append({
                    "tool_name": tool_name,
                    "tool_input": arguments,
                    "tool_output": output,
                    "call_id": call_id
                })
        
        return tool_calls

    def _prepare_context(self, result: List[Dict[str, Any]]) -> List[str]:
        """Extract context strings from tool outputs."""
        outputs = []

        for ctx in result:
            output = ctx.get("output") if "output" in ctx else None
            parsed_output = None
            if isinstance(output, str):
                try:
                    parsed_output = json.loads(output)
                except Exception:
                    try:
                        parsed_output = ast.literal_eval(output)
                    except Exception:
                        parsed_output = None
            elif isinstance(output, (list, dict)):
                parsed_output = output
            
            if parsed_output is not None:
                outputs.append({"data": parsed_output})

        context_list = []
        for entry in outputs:
            data = entry.get("data")
            if data is None:
                continue
                
            if isinstance(data, list):
                entities = data
            elif isinstance(data, dict):
                entities = [data]
            else:
                continue
                
            for entity in entities:
                if not isinstance(entity, dict):
                    continue
                    
                if "summary" in entity:
                    context = entity.get("summary", "")
                    doc_src = entity.get("document_sources", "")
                    context_list.append(f"{context} ---- {doc_src}".strip())
                elif "fact" in entity:
                    fact = entity.get("fact", "")
                    doc_src = entity.get("document_sources", "")
                    context_list.append(f"{fact} ---- {doc_src}".strip())
                elif "table_md" in entity:
                    chunk = entity.get("content", "")
                    table = entity.get("table_md", "")
                    doc_src = entity.get("title", "")
                    doc_page = entity.get("page", "")
                    context_list.append(f"{chunk} {table} ---- {doc_src}, page {doc_page}".strip())
                elif "formula_used" in entity:
                    kpi_name = entity.get("kpi_name", "")
                    formula = entity.get("formula_used", "")
                    inputs_received = entity.get("inputs_received", "")
                    context_list.append(f"KPI {kpi_name} calculated via formula: {formula} with inputs {inputs_received}".strip())
        
        return context_list

    def format_conversation_markdown(self, result: Dict[str, Any]) -> str:
        """
        Format the full conversation history as readable markdown.
        
        Args:
            result: The result dict from run_with_full_history
            
        Returns:
            Markdown formatted string of the conversation
        """
        lines = []
        lines.append(f"# Agent Conversation Log\n")
        lines.append(f"**Query:** {result.get('query', '')}\n")
        lines.append(f"**KPI:** {result.get('kpi_name', '')}\n")
        lines.append(f"**Year:** {result.get('year', '')}\n")
        lines.append("\n---\n")
        
        # Tool calls section
        lines.append("## Tool Calls\n")
        for i, tc in enumerate(result.get("tool_calls", []), 1):
            lines.append(f"### {i}. {tc.get('tool_name', 'Unknown Tool')}\n")
            lines.append(f"**Input:**\n```json\n{json.dumps(tc.get('tool_input', {}), indent=2)}\n```\n")
            output = tc.get('tool_output', {})
            if isinstance(output, list) and len(output) > 3:
                # Truncate long outputs for readability
                output_preview = output[:3]
                lines.append(f"**Output (first 3 of {len(output)}):**\n```json\n{json.dumps(output_preview, indent=2)}\n```\n")
            else:
                lines.append(f"**Output:**\n```json\n{json.dumps(output, indent=2, default=str)}\n```\n")
        
        # Final output section
        lines.append("\n---\n")
        lines.append("## Final Output\n")
        lines.append(f"```json\n{json.dumps(result.get('final_output', {}), indent=2)}\n```\n")
        
        return "\n".join(lines)

    def convert_to_ragas_messages(self, input_list: List[Dict[str, Any]], final_output: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Convert OpenAI SDK format input_list to RAGAS message format.
        
        Args:
            input_list: The input_list from response.to_input_list() in OpenAI format
            final_output: Optional final output dict from the agent (will be added as final AIMessage)
            
        Returns:
            List of RAGAS message objects (HumanMessage, AIMessage, ToolMessage, ToolCall)
        """
        # Import RAGAS message types here to avoid import errors if ragas not installed
        try:
            from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
        except ImportError:
            raise ImportError("ragas package is required. Install with: pip install ragas")
        
        ragas_messages = []
        
        # Build a map of call_id -> output for ToolMessages
        output_map = {}
        for item in input_list:
            if item.get("type") == "function_call_output":
                call_id = item.get("call_id")
                output = item.get("output", "")
                if call_id:
                    output_map[call_id] = output
        
        # Track pending tool calls to attach to AIMessage
        pending_tool_calls = []
        
        for item in input_list:
            item_type = item.get("type")
            role = item.get("role")
            
            # Human/User message
            if role == "user" or item_type == "message" and item.get("role") == "user":
                content = item.get("content", "")
                if isinstance(content, list):
                    # Handle content array format
                    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    content = " ".join(text_parts)
                ragas_messages.append(HumanMessage(content=str(content)))
                
            # Function call (tool invocation by assistant)
            elif item_type == "function_call":
                call_id = item.get("call_id")
                name = item.get("name", "")
                arguments = item.get("arguments", "{}")
                
                # Parse arguments if string
                if isinstance(arguments, str):
                    try:
                        args = json.loads(arguments)
                    except Exception:
                        args = {"raw": arguments}
                else:
                    args = arguments if isinstance(arguments, dict) else {}
                
                tool_call = ToolCall(name=name, args=args)
                pending_tool_calls.append((call_id, tool_call))
                
            # Function call output (tool result)
            elif item_type == "function_call_output":
                call_id = item.get("call_id")
                output = item.get("output", "")
                
                # Truncate long outputs
                if isinstance(output, str) and len(output) > 2000:
                    output = output[:2000] + "...[truncated]"
                elif not isinstance(output, str):
                    output = json.dumps(output, default=str)[:2000]
                
                ragas_messages.append(ToolMessage(content=str(output)))
                
            # Assistant message (may include tool_calls in OpenAI format)
            elif role == "assistant" or (item_type == "message" and item.get("role") == "assistant"):
                content = item.get("content", "")
                if isinstance(content, list):
                    text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
                    content = " ".join(text_parts)
                
                # Check if there are pending tool calls to attach
                if pending_tool_calls:
                    tool_calls_for_msg = [tc for _, tc in pending_tool_calls]
                    ragas_messages.append(AIMessage(
                        content=str(content) if content else "Calling tools...",
                        tool_calls=tool_calls_for_msg
                    ))
                    pending_tool_calls = []
                else:
                    ragas_messages.append(AIMessage(content=str(content)))
        
        # If there are remaining pending tool calls without an assistant message
        if pending_tool_calls:
            tool_calls_for_msg = [tc for _, tc in pending_tool_calls]
            ragas_messages.append(AIMessage(
                content="",
                tool_calls=tool_calls_for_msg
            ))
        
        # Add the final output as the last AIMessage if provided
        if final_output:
            # Format the final answer from the structured output
            final_answer_parts = []
            if final_output.get("kpi"):
                final_answer_parts.append(f"KPI: {final_output.get('kpi')}")
            if final_output.get("year"):
                final_answer_parts.append(f"Year: {final_output.get('year')}")
            if final_output.get("value"):
                final_answer_parts.append(f"Value: {final_output.get('value')}")
            if final_output.get("response"):
                final_answer_parts.append(f"Response: {final_output.get('response')}")
            if final_output.get("notes"):
                final_answer_parts.append(f"Notes: {final_output.get('notes')}")
            if final_output.get("source"):
                sources = final_output.get("source")
                if isinstance(sources, list):
                    source_strs = [f"{s.get('document', '')} page {s.get('page', '')}" for s in sources if isinstance(s, dict)]
                    final_answer_parts.append(f"Sources: {'; '.join(source_strs)}")
                elif isinstance(sources, dict):
                    final_answer_parts.append(f"Source: {sources.get('document', '')} page {sources.get('page', '')}")
                else:
                    final_answer_parts.append(f"Source: {sources}")
            
            final_content = "\n".join(final_answer_parts) if final_answer_parts else json.dumps(final_output, default=str)
            ragas_messages.append(AIMessage(content=final_content))
        
        return ragas_messages


async def main():

    log_level = logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        
        await initialize_graph()
        logger.info("Graph database initialized")

        graph_ok = await test_graph_connection()
        if not graph_ok:
            logger.error("Graph database connection test failed.")
    except Exception as e:
        logger.error(f"Failed to initialize graph database: {e}")
        raise
    try:
        initialize_database()
        logger.info("Vector database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize vector database: {e}")
        raise


    # PLEASE SET YOUR COMPANY HERE
    company = ""
    if company =="": logger.warning("Please set your company")
    #####

    client = company
    agent_info = AgentInfo(
        client=client,
        reranker_entity="RRF",
        reranker_fact="RRF",
        limit_vector_results=15,
        alpha_hybrid=0.6,
        limit_fact=30,
        limit_entity=10,
        k = 2
    )


    kpi_qualitative_speedboat = QualitativeKPIs_speedboat(client=client)
    query_qualitative_speedboat_list = kpi_qualitative_speedboat.all_queries_list()

    kpi_quantitative = QUANTITATIVE_KPIs_speedboat(client=client)
    # PLEASE ADJUST YEAR BASIS AND YEARS FOR QUANTITATIVE QUERIES AS NEEDED
    query_quantitative_speedboat_list = kpi_quantitative.all_queries_list(year_basis="", year_0 = 2025, year_1=2024, year_2=2023)

     # combine qualitative and quantitative queries
    query_complete = query_qualitative_speedboat_list + query_quantitative_speedboat_list

    try: 
        # treat each question independently
        response_user = ""
        response_user_list = []
        response_complete_input = []
        query_name = f"Report"
        with trace(f"Single Agent {company} - {query_name}"): 
            for q in  query_complete:
                    response = await Runner.run(
                    single_agent,
                    input= q,
                    context=agent_info
                    )
                    response_complete_input = response_complete_input + response.to_input_list()

                    # if using structured output
                    fo = response.final_output
                    if fo is None:
                        fo_dict = {}
                    else:
                        fo_dict = fo.model_dump()
                    response_user_list.append(fo_dict)
                        
                    # now use your formatter
                    # format_kpis_markdown expects a list of dicts.
                    if not fo_dict:
                        # nothing to append
                        continue
                    to_format = fo_dict if isinstance(fo_dict, list) else [fo_dict]
                    response_user += "\n" + format_kpis_markdown(to_format)

            markdown_table = make_markdown_table(response_user_list)       
            response_save = markdown_table 

            # create outputs folder inside the agent package directory
            agent_dir = os.path.dirname(__file__)
            outputs_dir = os.path.join(agent_dir, "outputs_single_agent")
            os.makedirs(outputs_dir, exist_ok=True)

            # build filename with date and time
            timestamp = datetime.now().strftime("%Y%m%d_%H")
            if len(response_user_list) == 1:
                filename = f"{client}_{response.final_output.kpi}_single_agent_{timestamp}.md"
            else:
                filename = f"{client}_single_agent_{timestamp}.md"
            filepath = os.path.join(outputs_dir, filename)

            # write final response to markdown file
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(response_save)
                logger.info(f"Final response saved to {filepath}")
            except Exception as e:
                logger.error(f"Failed to save final response: {e}")

    finally: 
        await close_graph()

        close_database()
        logger.info("Graph and vector database connections closed")



    



if __name__ == "__main__":
    asyncio.run(main())
