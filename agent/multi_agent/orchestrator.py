''' Orchestrator for Multi-Agent  '''
import os
import logging
import asyncio
import re
import json
import ast
from typing import Any, Dict, List, Optional
import logging
from dataclasses import dataclass, asdict
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, field_validator
from rich.console import Console
from agents import Agent, RunContextWrapper, Runner, function_tool, trace, gen_trace_id, custom_span
from agents.mcp.server import MCPServerStdio
from agents.extensions.visualization import draw_graph
import shutil
from .derived_kpi_agent import derived_kpi_agent
from .retrieval_agent_quantitative import retrieval_agent_quantitative
from .retrieval_agent_qualitative import retrieval_agent_qualitative
from .review_agent import review_agent
from .writer_agent import writer_agent
from .router_agent import router_agent
from ..graph_utils import initialize_graph, test_graph_connection, close_graph
from ..vector_db_utils import initialize_database, close_database
from ..query_qualtitative_kpi import QualitativeKPIs_speedboat
from ..query_quantitative_kpi import QUANTITATIVE_KPIs_speedboat

from ..models import AgentInfoBasic, AgentInfo
from agent.multi_agent_rwr.printer import Printer

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)



# Orchestrator via Code
class create_credit_risk_report:
    def __init__(self) -> None:
        self.console = Console()
        self.printer = Printer(console=self.console)
    
    async def run(self, client: str, agent_info: AgentInfo, query_list: list[str], description: Optional[str]= "") -> None:
        """ Run the full multi-agent process """

        trace_id = gen_trace_id()

        if client == "default_client": company = "RWE"
        else: company = client

        with trace(f"{company} Multi Agent ", trace_id=trace_id):
            self.printer.update_item(
                trace_id,
                f"",
                is_done=True,
                hide_checkmark=True,
            )

            # Step 1: KPI Extraction
            self.printer.update_item("start", "Starting Pipeline", is_done=True)

            kpi_extraction = await self.kpi_extraction_task(agent_info, query_list)

            #Step 2: Report Writing
            self.printer.update_item("report_writing", "Report writing...", is_done=True)
            writer_input = [{"role": "user", "content": json.dumps(kpi_extraction)}]
            report = await Runner.run(
                writer_agent,
                writer_input,
                context=agent_info,
            )
            
            

            # Review Step 
            review_round = 1
            MAX_REVIEW_ROUNDS = 3
            report_review_input = report.to_input_list()
            writer_result = report
            #self.printer.mark_item_done("report_writing")
            # while review_round <= MAX_REVIEW_ROUNDS:
            #     self.save_report(f"{writer_result.final_output.report}", suffix=f"version_{review_round}")
            #     self.printer.update_item("report_review", "Report review...", is_done=True)
            #     # review_input = [{
            #     #     "role": "user", 
            #     #     "content": [{"type": "text", "text": report_review_input}]
            #     # }]
            #     review_result = await Runner.run(
            #         review_agent,
            #         report_review_input)
                
            #     if review_result.final_output.passed:
            #         self.printer.mark_item_done("report_review")
            #         break
            #     else:
            #         review_round += 1
            #         # Wrap the action_plan in a proper message format with content array
            #         writer_input = review_result.to_input_list()
            #         writer_result = await Runner.run(
            #             writer_agent,
            #             writer_input,
            #             context=agent_info,
            #         )
            #         report_review_input = writer_result.to_input_list()
            #         self.printer.update_item("report_review", f"Report review... (Round {review_round-1} completed)", is_done=True)   

            self.save_report(client =company, report=f"{writer_result.final_output.report}", suffix=description)
            self.printer.end()


    async def kpi_extraction_task(self, agent_info: AgentInfo, query_list: list[str]) -> List[Dict[str, Any]]:
        """ Task to extract KPIs using retrieval agents """
        with custom_span("KPI Extraction Task"):
            self.printer.update_item("kpi_extraction", "KPI extraction...\n")
            tasks = [asyncio.create_task(self._search_kpi(agent_info, query)) for query in query_list]
            results: list[Dict[str, Any]] = []
            num_completed = 0
            for task in asyncio.as_completed(tasks):
                kpi_result = await task
                if kpi_result is not None:
                    # kpi_result is a list; flatten into results
                    results.extend(kpi_result)
                num_completed += 1
                self.printer.update_item(
                    "kpi_extraction",
                    f"KPI extraction... ({num_completed}/{len(query_list)})",
                )
        self.printer.mark_item_done("kpi_extraction")

        return results


    async def _search_kpi(self, agent_info: AgentInfo, query: str) -> Optional[tuple[List[Dict[str, Any]], List]]:
        """ Search for a single KPI using the retrieval agent """
        results = []
        context_sample = []
        router_inputs = []
        try:
            # Step 1: Router Agent to decide which retrieval agent to use
            router_result = await Runner.run(
                router_agent,
                query,
                context=agent_info,
            )
            router_inputs = router_result.to_input_list()

            ro = self.normalize_router_output(router_result.final_output)
            
            if ro["category"] in ["single_quantitative", "multiple_quantitative"]:
                for item in ro["quantitative_items"]:
                    # normalize item to dict
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    # enrich with entity and fiscal year
                    item_payload["entity"] = ro.get("entity")
                    item_payload["requested_year"] = ro.get("requested_year")
                    item_payload["fiscal_year_basis"] = ro.get("fiscal_year_basis")
                    item_payload["mapped_fiscal_year"] = ro.get("mapped_fiscal_year")
                    item_payload["reporting_year_end"] = ro.get("reporting_year_end")

                    # build per-item retrieval payload
                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}

                    retrieval_result = await Runner.run(
                        retrieval_agent_quantitative,
                        [input_item],
                        context=agent_info,
                    )

                    # normalize result
                    result_dict = (retrieval_result.final_output.model_dump()
                                   if hasattr(retrieval_result.final_output, "model_dump")
                                   else retrieval_result.final_output)
                    
                    
                    if result_dict.get("status") == "not_found":
                        derived_result = await Runner.run(
                            derived_kpi_agent,
                            [input_item],
                            context=agent_info,
                        )
                        derived_dict = (derived_result.final_output.model_dump()
                                        if hasattr(derived_result.final_output, "model_dump")
                                        else derived_result.final_output)
                        results.append(derived_dict)
                    else:
                        results.append(result_dict)

            if ro["category"] == "qualitative":
                for item in ro["qualitative_items"]:
                    # normalize item to dict
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    # enrich with entity and fiscal year
                    item_payload["entity"] = ro.get("entity")
                    item_payload["requested_year"] = ro.get("requested_year")
                    item_payload["fiscal_year_basis"] = ro.get("fiscal_year_basis")
                    item_payload["mapped_fiscal_year"] = ro.get("mapped_fiscal_year")
                    item_payload["reporting_year_end"] = ro.get("reporting_year_end")

                    # build per-item retrieval payload
                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}
                    print(f"Input item for retrieval agent: {input_item}")

                    retrieval_result = await Runner.run(
                        retrieval_agent_qualitative,
                        [input_item],
                        context=agent_info,
                    )
                    
                    result_dict = (retrieval_result.final_output.model_dump() 
                                  if hasattr(retrieval_result.final_output, 'model_dump') 
                                  else retrieval_result.final_output)
                    results.append(result_dict)
                
        except Exception as e:
            logger.error(f"Error searching KPI for query '{query}': {e}", exc_info=True)
        
        return results
        

    def save_report(self, client: str, report: str, suffix: Optional[str] = "") -> None:
        """ Save the generated report to a file """
        # create outputs folder inside the agent package directory
        agent_dir = os.path.dirname(__file__)
        outputs_dir = os.path.join(agent_dir, "outputs_multi_agent")
        os.makedirs(outputs_dir, exist_ok=True)

        response_save = f"## Report\n\n{report}\n\n"

        # build filename with date and time
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{client}_multi_agent_{timestamp}_{suffix}.md"
        filepath = os.path.join(outputs_dir, filename)

        # write final response to markdown file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response_save)
            logger.info(f"Final response saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save final response: {e}")
    def normalize_router_output(self, ro):
        return ro.model_dump() if hasattr(ro, "model_dump") else dict(ro)

        
    def build_retrieval_payload(self, item, ro):
        item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)

        return {
            "kpi_name": item_dict["kpi_canonical_name"],
            "entity": ro["entity"],
            "fiscal_year": ro.get("fiscal_year"),
        }
    

# For Evaluation (for RAGAS evaluation)
class multi_agent_router_orchestrator_run:

    def __init__(self, client: str = "default_client", 
                reranker_entity: str = "RRF", 
                reranker_fact: str = "RRF", 
                limit_vector_results: int = 15,
                alpha_hybrid: float = 0.5,
                limit_fact: int = 30,
                limit_entity: int = 20,
                k: int = 2          
                ) -> None:
        self.console = Console()
        self.printer = Printer(console=self.console)
        self.client = client
        self.reranker_entity = reranker_entity
        self.reranker_fact = reranker_fact
        self.limit_vector_results = limit_vector_results
        self.alpha_hybrid = alpha_hybrid
        self.limit_fact = limit_fact
        self.limit_entity = limit_entity
        self.k = k

    async def run_eval(self, queries: list[str], kpi_expected_name: Optional[str]) -> Dict[str, Any]:
        """ Run the full multi-agent process and return combined context (router + retrieval samples) """

        trace_id = gen_trace_id()
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
        
        company = self.client

        with trace(f" Multi Agent Eval {company} {kpi_expected_name}", trace_id=trace_id):
            self.printer.update_item(
                trace_id,
                f"",
                is_done=True,
                hide_checkmark=True,
            )

            query = queries[0] if queries else ""

            # Default payload so we never crash on return
            results_eval: Dict[str, Any] = {
                "kpi_name": "",
                "year": "",
                "query": query,
                "quantitative_findings": "",
                "quantitative_context": [],
                "qualitative_findings": "",
                "type_retrieval": "unknown",
                "qualitative_context": [],
                "report": "",
                "all_contexts": "",
            }

            try:
                # Step 1: KPI Extraction
                self.printer.update_item("start", "Starting Pipeline", is_done=True)

                kpi_extraction, type_retrieval, context_sample = await self.kpi_extraction_task(agent_info, queries)

                # Step 2: Report Writing
                self.printer.update_item("report_writing", "Report writing...", is_done=True)
                writer_input = [{"role": "user", "content": json.dumps(kpi_extraction)}]
                report = await Runner.run(
                    writer_agent,
                    writer_input,
                    context=agent_info,
                )

                kpi_name = ""
                year: Any = ""
                for result in kpi_extraction:
                    if isinstance(result, dict):
                        kpi_name = result.get("kpi_name", kpi_name) or kpi_name
                        year = result.get("year") or result.get("fiscal_year_retrieved") or year

                # Format KPI extraction results into strings
                kpi_extraction_formatted: Any = self._format_kpi_extraction(kpi_extraction)
                if isinstance(kpi_extraction_formatted, list) and len(kpi_extraction_formatted) == 1:
                    kpi_extraction_formatted = kpi_extraction_formatted[0]

                results_eval = {
                    "kpi_name": kpi_name,
                    "year": year,
                    "query": query,
                    "quantitative_findings": kpi_extraction_formatted if type_retrieval == "quantitative" else "",
                    "quantitative_context": context_sample if type_retrieval == "quantitative" else [],
                    "qualitative_findings": kpi_extraction_formatted if type_retrieval == "qualitative" else "",
                    "type_retrieval": type_retrieval,
                    "qualitative_context": context_sample if type_retrieval == "qualitative" else [],
                    "report": report.final_output.report,
                    "all_contexts": kpi_extraction_formatted,
                }
            except Exception as e:
                logger = logging.getLogger(__name__)
                logger.error(f"run_eval failed for query '{query}': {e}", exc_info=True)
                results_eval["error"] = str(e)


            
            #self.printer.mark_item_done("report_writing")
            # while review_round <= MAX_REVIEW_ROUNDS:
            #     self.save_report(f"{writer_result.final_output.report}", suffix=f"version_{review_round}")
            #     self.printer.update_item("report_review", "Report review...", is_done=True)
            #     # review_input = [{
            #     #     "role": "user", 
            #     #     "content": [{"type": "text", "text": report_review_input}]
            #     # }]
            #     review_result = await Runner.run(
            #         review_agent,
            #         report_review_input)
                
            #     if review_result.final_output.passed:
            #         self.printer.mark_item_done("report_review")
            #         break
            #     else:
            #         review_round += 1
            #         # Wrap the action_plan in a proper message format with content array
            #         writer_input = review_result.to_input_list()
            #         writer_result = await Runner.run(
            #             writer_agent,
            #             writer_input,
            #             context=agent_info,
            #         )
            #         report_review_input = writer_result.to_input_list()
            #         self.printer.update_item("report_review", f"Report review... (Round {review_round-1} completed)", is_done=True)   

            if results_eval.get("report"):
                self.save_report(str(results_eval.get("report")), prefix=company,suffix=kpi_expected_name)
            self.printer.end()

            return results_eval


    async def kpi_extraction_task(self, agent_info: AgentInfo, query_list: list[str]) -> tuple[List[Dict[str, Any]], str, List[str]]:
        """ Task to extract KPIs using retrieval agents """
        with custom_span("KPI Extraction Task"):
            self.printer.update_item("kpi_extraction", "KPI extraction...\n")
            tasks = [asyncio.create_task(self._search_kpi(agent_info, query)) for query in query_list]
            results: list[Dict[str, Any]] = []
            router_inputs_all = []
            context_retrieval_samples: List[str] = []
            type_retrieval = "unknown"
            num_completed = 0
            for task in asyncio.as_completed(tasks):
                kpi_result = await task
                if kpi_result is not None:
                    # kpi_result is a tuple of (results, router_inputs)
                    results.extend(kpi_result[0])
                    #router_inputs_all.extend(kpi_result[1])
                    context_retrieval_samples.extend(kpi_result[1])
                    type_retrieval = kpi_result[2]
                num_completed += 1
                self.printer.update_item(
                    "kpi_extraction",
                    f"KPI extraction... ({num_completed}/{len(query_list)})",
                )
                
        self.printer.mark_item_done("kpi_extraction")

        return results, type_retrieval, context_retrieval_samples


    async def _search_kpi(self, agent_info: AgentInfo, query: str) -> tuple[List[Dict[str, Any]], List[str], str]:
        # --- FIX: initialize to avoid UnboundLocalError on non-derived paths ---
        source_str_derived: str = ""
        source_str_vector: str = ""

        # (keep your existing initializations too)
        results: List[Dict[str, Any]] = []
        context_sample: List[str] = []
        type_retrieval: str = ""

        try:
            # Step 1: Router Agent to decide which retrieval agent to use
            router_result = await Runner.run(
                router_agent,
                query,
                context=agent_info,
            )
            router_input = self._prepare_context(router_result.to_input_list(), agent_tool="Agent")
  
            ro = self.normalize_router_output(router_result.final_output)
            
            if ro["category"] in ["single_quantitative", "multiple_quantitative", "mixed"]:
                type_retrieval = "quantitative"
                for item in ro["quantitative_items"]:
                    # normalize item to dict
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    # enrich with entity and fiscal year
                    item_payload["entity"] = ro.get("entity")
                    item_payload["requested_year"] = ro.get("requested_year")
                    item_payload["mapped_fiscal_year"] = ro.get("mapped_fiscal_year")

                    # build per-item retrieval payload
                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}

                    retrieval_result = await Runner.run(
                        retrieval_agent_quantitative,
                        [input_item],
                        context=agent_info,
                    )

                    # Keep context a flat list[str] (router + tool context)
                    context_sample.extend(router_input)
                    context_sample.extend(self._prepare_context(retrieval_result.to_input_list(), agent_tool="Tool"))

                    # normalize result
                    result_dict = (retrieval_result.final_output.model_dump()
                                   if hasattr(retrieval_result.final_output, "model_dump")
                                   else retrieval_result.final_output)
                    
                    
                    # --- FIX: build vector source string safely (or leave empty) ---
                    if isinstance(result_dict, dict):
                        doc = result_dict.get("document_sources") or result_dict.get("sources") or ""
                        title = result_dict.get("title") or ""
                        page = result_dict.get("page") or ""
                        source_str_vector = " ".join(str(x).strip() for x in [title, page, doc] if str(x).strip())

                    if isinstance(result_dict, dict) and result_dict.get("status") == "not_found":
                        derived_result = await Runner.run(
                            derived_kpi_agent,
                            [input_item],
                            context=agent_info,
                        )

                        derived_dict = (
                            derived_result.final_output.model_dump()
                            if hasattr(derived_result.final_output, "model_dump")
                            else derived_result.final_output
                        )

                        context_sample.extend(self._prepare_context(derived_result.to_input_list(), agent_tool="Agent"))


                        # --- FIX: build derived source string safely (or leave empty) ---
                        if isinstance(derived_dict, dict):
                            doc = derived_dict.get("document_sources") or derived_dict.get("sources") or ""
                            title = derived_dict.get("title") or ""
                            page = derived_dict.get("page") or ""
                            source_str_derived = " ".join(str(x).strip() for x in [title, page, doc] if str(x).strip())

                        results.append(derived_dict)
                    else:
                        results.append(result_dict)

            if ro["category"] in ["qualitative", "mixed"]:
                type_retrieval = "qualitative"
                for item in ro["qualitative_items"]:
                    # normalize item to dict
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    # enrich with entity and fiscal year
                    item_payload["entity"] = ro.get("entity")
                    item_payload["fiscal_year"] = ro.get("fiscal_year")

                    # build per-item retrieval payload
                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}

                    retrieval_result = await Runner.run(
                        retrieval_agent_qualitative,
                        [input_item],
                        context=agent_info,
                    )

                    # Keep context a flat list[str] (router + tool context)
                    context_sample.extend(router_input)
                    context_sample.extend(self._prepare_context(retrieval_result.to_input_list(), agent_tool="Tool"))

                    result_dict = (retrieval_result.final_output.model_dump() 
                                  if hasattr(retrieval_result.final_output, 'model_dump') 
                                  else retrieval_result.final_output)
                    results.append(result_dict)
                
        except Exception as e:
            logger.error(f"Error searching KPI for query '{query}': {e}", exc_info=True)
        # --- FIX: never reference source_str_derived unless it exists (now always exists anyway) ---
        return results, context_sample, type_retrieval
        

    def save_report(self, report: str, prefix: Optional[str]="",suffix: Optional[str] = "") -> None:
        """ Save the generated report to a file """
        # create outputs folder inside the agent package directory
        agent_dir = os.path.dirname(__file__)
        timestamp = datetime.now().strftime("%Y%m%d_%H%")
        outputs_dir = os.path.join(agent_dir, f"outputs/eval/{timestamp}")
        os.makedirs(outputs_dir, exist_ok=True)

        response_save = f"## Report\n\n{report}\n\n"

        # build filename with date and time
        
        filename = f"{prefix}_{suffix}_eval_multi_agent_{timestamp}.md"
        filepath = os.path.join(outputs_dir, filename)

        # write final response to markdown file
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(response_save)
            logger.info(f"Final response saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save final response: {e}")
    def normalize_router_output(self, ro):
        return ro.model_dump() if hasattr(ro, "model_dump") else dict(ro)      
    def build_retrieval_payload(self, item, ro):
        item_dict = item.model_dump() if hasattr(item, "model_dump") else dict(item)

        return {
            "kpi_name": item_dict["kpi_canonical_name"],
            "entity": ro["entity"],
            "requested_year": ro.get("requested_year"),
            "mapped_fiscal_year": ro.get("mapped_fiscal_year"),
        }
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
            for i, entity in enumerate(entities):
                if not isinstance(entity, dict):
                    continue
                    
                if "summary" in entity:
                    # Entity retrieval context
                    context = entity.get("summary", "")
                    #doc_src = entity.get("document_sources", "")
                    context_list.append(f"{context}")  #---{doc_src}".strip())
                elif "fact" in entity:
                    # Fact retrieval context
                    fact = entity.get("fact", "")
                    doc_src = entity.get("document_sources", "")
                    context_list.append(f"{fact} ") # ---- {doc_src}".strip())

                elif "content" in entity:
                    # Vector DB retrieval context
                    chunk = entity.get("content", "")
                    table = entity.get("table_md", "")
                    doc_src = entity.get("title", "")
                    doc_page = entity.get("page", "")
                    context_list.append(f"{chunk} {table} ---- {doc_src}, page {doc_page}".strip())
                elif "formula_used" in entity:
                    # KPI calculation context
                    kpi_name = entity.get("kpi_name", "")
                    value = entity.get("value", "")
                    formula = entity.get("formula_used", "")
                    inputs_received = entity.get("inputs_received", "")
                    context_list.append(f"KPI {kpi_name} {value} calculated via formula: {formula} with inputs {inputs_received}".strip())   

                elif "value" in entity:
                    # Quantitative KPI retrieval context
                    kpi_name = entity.get("kpi_name", "")
                    value = entity.get("value", "")
                    unit = entity.get("unit", "")
                    source = entity.get("source", "")
                    fiscal_year = entity.get("fiscal_year", "")
                    notes = entity.get("notes", "")
                    context_list.append(f"KPI {kpi_name} with value: {value} {unit} (Source: {source}, Fiscal Year: {fiscal_year}, Notes: {notes})".strip())
                
                # elif "category" in entity:
                #     # Router decision context
                #     category = entity.get("category", "")
                #     entity_name = entity.get("entity", "")
                #     requested_year = entity.get("requested_year", "")
                #     mapped_fiscal_year = entity.get("mapped_fiscal_year", "")
                #     qualitative_items = entity.get("qualitative_items", "")
                #     quantitative_items = entity.get("quantitative_items", "")
                #     context_list.append(f"Router decision: category {category} for entity {entity_name} in requested year {requested_year} mapped fiscal year {mapped_fiscal_year} with qualitative items {qualitative_items} and quantitative items {quantitative_items}".strip())
        return context_list
    def _format_kpi_extraction(self, kpi_extraction: List[Dict[str, Any]]) -> List[str]:
        """
        Transform KPI extraction results into formatted strings containing
        entity, themes, summary, findings, and sources.
        """
        formatted_results = []
        
        for kpi in kpi_extraction:
            parts = []
            
            # Entity
            entity = kpi.get("entity", "")
            if entity != "":
                parts.append(f"Entity: {entity}")

            # KPI Name
            kpi_name = kpi.get("kpi_name", "")
            if kpi_name != "": 
                parts.append(f"KPI : {kpi_name}")
            
            # Themes (for qualitative KPIs)
            themes = kpi.get("themes", "")
            #if themes:
            #    parts.append(f"Themes: {themes}")
            
            # Summary
            summary = kpi.get("summary", "")
            if summary:
                parts.append(f"Summary: {summary}")
            
            fact = kpi.get("fact", "")
            if fact:
                parts.append(f"Fact: {fact}")
            
            # Findings (for qualitative KPIs)
            findings = kpi.get("findings", [])
            if findings:
                findings_str = []
                for finding in findings:
                    if isinstance(finding, dict):
                        finding_type = finding.get("type", "")
                        content = finding.get("content", "")
                        source = finding.get("source", {})
                        if isinstance(source, dict):
                            doc_title = source.get("document_title", "")
                            page_num = source.get("page_number", "")
                            source_str = f"{doc_title}, page {page_num}" if page_num else doc_title
                        else:
                            source_str = str(source)
                        findings_str.append(f"[{finding_type}] {content} (Source: {source_str})")
                parts.append(f"Findings: {'; '.join(findings_str)}")
            
            # Source (for quantitative KPIs)
            source = kpi.get("source", {})
            if source:
                if isinstance(source, dict):
                    doc_title = source.get("document_title", "")
                    page_num = source.get("page_number", "")
                    source_str = f"{doc_title}, page {page_num}" if page_num else doc_title
                    parts.append(f"Source: {source_str}")
            
            # Value and Unit (for quantitative KPIs)
            value = kpi.get("value", "")
            unit = kpi.get("unit", "")
            notes = kpi.get("notes", "")

            # Derived KPIs
            derived_from_list = kpi.get("derived_from", [])
            derived_from_info= "Derived from intermediate KPIs: "
            if derived_from_list:
                for item in derived_from_list:
                    kpi_name_derived = item.get("kpi_name", "")
                    value_derived = item.get("value", "")
                    unit_derived  = item.get("unit", "")
                    kpi_value_derived = f"{value_derived} {unit_derived}".strip()
                    source_derived = item.get("source", {})
                    source_str_derived = ""
                    if isinstance(source_derived, dict):
                        doc_title_derived = source_derived.get("title", "")
                        page_num_derived = source_derived.get("page", "")
                        source_str_derived = f"{doc_title_derived}, page {page_num_derived}" if page_num_derived else doc_title_derived
                    else:
                        source_str_derived = str(source_derived) if source_derived else ""
                    derived_from_info += f"{kpi_name_derived} = {kpi_value_derived} ({source_str_derived}), "
            formula_used = kpi.get("formula_used", "")
            if formula_used: 
                derived_from_info += f" calculated by formula: {formula_used}. "

            if value:
                value_str = f"{value} {unit}".strip()
                parts.append(f"Value: {value_str}")
            if derived_from_list:
                parts.append(f"{derived_from_info}")
            if notes != "": parts.append(f"Notes: {notes}")
            
            # Combine all parts into a single string
            formatted_results.append(" | ".join(parts))


        
        return formatted_results


# Class for multi-agent with full conversation history (for AGA evaluation)
class multi_agent_router_orchestrator_run_input_list:
    """
    Similar to multi_agent_router_orchestrator_run but returns the complete conversation history
    including all agent messages, tool inputs, tool outputs, etc. for RAGAS evaluation.
    """

    def __init__(self, 
                client: str = "default_client", 
                reranker_entity: str = "RRF", 
                reranker_fact: str = "RRF", 
                limit_vector_results: int = 15,
                alpha_hybrid: float = 0.5,
                limit_fact: int = 30,
                limit_entity: int = 20,
                k: int = 2          
                ) -> None:
        self.console = Console()
        self.printer = Printer(console=self.console)
        self.client = client
        self.reranker_entity = reranker_entity
        self.reranker_fact = reranker_fact
        self.limit_vector_results = limit_vector_results
        self.alpha_hybrid = alpha_hybrid
        self.limit_fact = limit_fact
        self.limit_entity = limit_entity
        self.k = k
        # Store all input_lists from each agent run
        self.all_input_lists: List[Dict[str, Any]] = []

    async def run_with_full_history(self, queries: list[str], kpi_expected_name: Optional[str]="") -> Dict[str, Any]:
        """
        Run the multi-agent pipeline and return full conversation history.
        
        Returns:
            Dict containing:
                - query: The original query
                - final_output: The final KPI output/report
                - input_list: Combined conversation history from all agents
                - agent_traces: Detailed traces per agent (router, retrieval, writer)
                - kpi_name: Extracted KPI name
                - year: Extracted year
        """
        trace_id = gen_trace_id()
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


        query = queries[0] if queries else ""
        self.all_input_lists = []
        agent_traces: List[Dict[str, Any]] = []
        if self.client == "default_client": company = "RWE" 
        else: company = self.client

        try:
            with trace(f"{company} {kpi_expected_name} Multi Agent Eval", trace_id=trace_id):
                self.printer.update_item(trace_id, "", is_done=True, hide_checkmark=True)
                self.printer.update_item("start", "Starting Pipeline", is_done=True)

                # Step 1: KPI Extraction with full history
                kpi_extraction, type_retrieval, agent_traces = await self._kpi_extraction_with_history(agent_info, queries)

                # Step 2: Report Writing
                self.printer.update_item("report_writing", "Report writing...", is_done=True)
                writer_input = [{"role": "user", "content": json.dumps(kpi_extraction)}]
                report_result = await Runner.run(
                    writer_agent,
                    writer_input,
                    context=agent_info,
                )

                # Store writer input list
                writer_input_list = report_result.to_input_list()
                self.all_input_lists.append({
                    "agent": "writer_agent",
                    "input_list": writer_input_list
                })
                agent_traces.append({
                    "agent": "writer_agent",
                    "input_list": writer_input_list,
                    "final_output": report_result.final_output.model_dump() if hasattr(report_result.final_output, 'model_dump') else {}
                })

                # Extract kpi_name and year from results
                kpi_name = ""
                year: Any = ""
                for result in kpi_extraction:
                    if isinstance(result, dict):
                        kpi_name = result.get("kpi_name", kpi_name) or kpi_name
                        year = result.get("year") or result.get("fiscal_year_retrieved") or year

                # Get final output
                final_output = {}
                if hasattr(report_result.final_output, 'model_dump'):
                    final_output = report_result.final_output.model_dump()
                elif hasattr(report_result.final_output, '__dict__'):
                    final_output = report_result.final_output.__dict__

                # Combine all input_lists into a single list
                combined_input_list = self._combine_input_lists()

                self.printer.end()

                return {
                    "query": query,
                    "final_output": final_output,
                    "input_list": combined_input_list,
                    "agent_traces": agent_traces,
                    "kpi_extraction": kpi_extraction,
                    "type_retrieval": type_retrieval,
                    "kpi_name": kpi_name,
                    "year": year,
                    "report": final_output.get("report", ""),
                }

        except Exception as e:
            logger.error(f"Error during multi-agent run: {e}", exc_info=True)
            self.printer.end()
            return {
                "query": query,
                "final_output": {},
                "input_list": [],
                "agent_traces": [],
                "kpi_extraction": [],
                "type_retrieval": "",
                "kpi_name": "",
                "year": "",
                "error": str(e)
            }

    async def _kpi_extraction_with_history(self, agent_info: AgentInfo, query_list: list[str]) -> tuple[List[Dict[str, Any]], str, List[Dict[str, Any]]]:
        """KPI extraction that captures full conversation history from each agent."""
        with custom_span("KPI Extraction Task"):
            self.printer.update_item("kpi_extraction", "KPI extraction...\n")
            
            results: List[Dict[str, Any]] = []
            agent_traces: List[Dict[str, Any]] = []
            type_retrieval = "unknown"
            
            for query in query_list:
                kpi_result = await self._search_kpi_with_history(agent_info, query)
                if kpi_result is not None:
                    results.extend(kpi_result[0])
                    agent_traces.extend(kpi_result[1])
                    type_retrieval = kpi_result[2]
                    
            self.printer.mark_item_done("kpi_extraction")
            
        return results, type_retrieval, agent_traces

    async def _search_kpi_with_history(self, agent_info: AgentInfo, query: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """Search for KPI with full history capture."""
        results: List[Dict[str, Any]] = []
        agent_traces: List[Dict[str, Any]] = []
        type_retrieval: str = "unknown"

        try:
            # Step 1: Router Agent
            router_result = await Runner.run(
                router_agent,
                query,
                context=agent_info,
            )
            router_input_list = router_result.to_input_list()
            
            self.all_input_lists.append({
                "agent": "router_agent",
                "input_list": router_input_list
            })
            agent_traces.append({
                "agent": "router_agent",
                "input_list": router_input_list,
                "final_output": router_result.final_output.model_dump() if hasattr(router_result.final_output, 'model_dump') else {}
            })

            ro = router_result.final_output.model_dump() if hasattr(router_result.final_output, "model_dump") else dict(router_result.final_output)

            # Process quantitative items
            if ro.get("category") in ["single_quantitative", "multiple_quantitative", "mixed"]:
                type_retrieval = "quantitative"
                for item in ro.get("quantitative_items", []):
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    item_payload["entity"] = ro.get("entity")
                    item_payload["requested_year"] = ro.get("requested_year")
                    item_payload["mapped_fiscal_year"] = ro.get("mapped_fiscal_year")

                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}

                    retrieval_result = await Runner.run(
                        retrieval_agent_quantitative,
                        [input_item],
                        context=agent_info,
                    )

                    retrieval_input_list = retrieval_result.to_input_list()
                    self.all_input_lists.append({
                        "agent": "retrieval_agent_quantitative",
                        "input_list": retrieval_input_list
                    })
                    agent_traces.append({
                        "agent": "retrieval_agent_quantitative",
                        "input_list": retrieval_input_list,
                        "final_output": retrieval_result.final_output.model_dump() if hasattr(retrieval_result.final_output, 'model_dump') else {}
                    })

                    result_dict = retrieval_result.final_output.model_dump() if hasattr(retrieval_result.final_output, "model_dump") else retrieval_result.final_output

                    # Check if derived KPI agent is needed
                    if isinstance(result_dict, dict) and result_dict.get("status") == "not_found":
                        derived_result = await Runner.run(
                            derived_kpi_agent,
                            [input_item],
                            context=agent_info,
                        )
                        derived_input_list = derived_result.to_input_list()
                        self.all_input_lists.append({
                            "agent": "derived_kpi_agent",
                            "input_list": derived_input_list
                        })
                        agent_traces.append({
                            "agent": "derived_kpi_agent",
                            "input_list": derived_input_list,
                            "final_output": derived_result.final_output.model_dump() if hasattr(derived_result.final_output, 'model_dump') else {}
                        })
                        derived_dict = derived_result.final_output.model_dump() if hasattr(derived_result.final_output, "model_dump") else derived_result.final_output
                        results.append(derived_dict)
                    else:
                        results.append(result_dict)

            # Process qualitative items
            if ro.get("category") in ["qualitative", "mixed"]:
                type_retrieval = "qualitative"
                for item in ro.get("qualitative_items", []):
                    item_payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
                    item_payload["entity"] = ro.get("entity")
                    item_payload["fiscal_year"] = ro.get("fiscal_year")

                    retrieval_payload = {"kpis": [item_payload]}
                    input_item = {"role": "user", "content": json.dumps(retrieval_payload)}

                    retrieval_result = await Runner.run(
                        retrieval_agent_qualitative,
                        [input_item],
                        context=agent_info,
                    )

                    retrieval_input_list = retrieval_result.to_input_list()
                    self.all_input_lists.append({
                        "agent": "retrieval_agent_qualitative",
                        "input_list": retrieval_input_list
                    })
                    agent_traces.append({
                        "agent": "retrieval_agent_qualitative",
                        "input_list": retrieval_input_list,
                        "final_output": retrieval_result.final_output.model_dump() if hasattr(retrieval_result.final_output, 'model_dump') else {}
                    })

                    result_dict = retrieval_result.final_output.model_dump() if hasattr(retrieval_result.final_output, 'model_dump') else retrieval_result.final_output
                    results.append(result_dict)

        except Exception as e:
            logger.error(f"Error searching KPI for query '{query}': {e}", exc_info=True)

        return results, agent_traces, type_retrieval

    def _combine_input_lists(self) -> List[Dict[str, Any]]:
        """Combine all input_lists into a single chronological list."""
        combined = []
        for entry in self.all_input_lists:
            agent_name = entry.get("agent", "unknown")
            for item in entry.get("input_list", []):
                # Add agent marker to each item
                item_with_agent = {**item, "_agent": agent_name}
                combined.append(item_with_agent)
        return combined

    def convert_to_ragas_messages(self, input_list: List[Dict[str, Any]], final_output: Optional[Dict[str, Any]] = None) -> List[Any]:
        """
        Convert OpenAI SDK format input_list to RAGAS message format.
        Same as single_agent_run_input_list.convert_to_ragas_messages()
        """
        from ragas.messages import AIMessage, HumanMessage, ToolCall, ToolMessage
        
        ragas_messages = []
        
        # Build tool output map
        tool_outputs = {}
        for item in input_list:
            if item.get("type") == "function_call_output":
                call_id = item.get("call_id")
                output = item.get("output", "")
                if call_id:
                    tool_outputs[call_id] = output
        
        for item in input_list:
            role = item.get("role")
            item_type = item.get("type")
            
            if role == "user":
                content = item.get("content", "")
                if isinstance(content, list):
                    text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                    content = " ".join(text_parts)
                ragas_messages.append(HumanMessage(content=str(content)))
                
            elif role == "assistant" or item_type == "function_call":
                if item_type == "function_call":
                    tool_name = item.get("name", "")
                    arguments = item.get("arguments", "{}")
                    call_id = item.get("call_id", "")
                    
                    if isinstance(arguments, str):
                        try:
                            args_dict = json.loads(arguments)
                        except Exception:
                            args_dict = {"raw": arguments}
                    else:
                        args_dict = arguments
                    
                    tool_call = ToolCall(name=tool_name, args=args_dict)
                    
                    # Get output
                    output = tool_outputs.get(call_id, "")
                    
                    # Add AIMessage with tool call
                    ragas_messages.append(AIMessage(
                        content="",
                        tool_calls=[tool_call]
                    ))
                    
                    # Add ToolMessage with result
                    ragas_messages.append(ToolMessage(
                        content=str(output)[:5000] if output else ""
                    ))
                else:
                    content = item.get("content", "")
                    if isinstance(content, list):
                        text_parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
                        content = " ".join(text_parts)
                    if content:
                        ragas_messages.append(AIMessage(content=str(content)))
        
        # Add final output as final AIMessage
        if final_output:
            report = final_output.get("report", "")
            kpi_name = final_output.get("kpi_name", "")
            value = final_output.get("value", "")
            
            if report:
                final_content = report
            else:
                parts = []
                if kpi_name:
                    parts.append(f"KPI: {kpi_name}")
                if value:
                    parts.append(f"Value: {value}")
                final_content = " | ".join(parts) if parts else str(final_output)
            
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
    company = "RWE"
    agent_info = AgentInfo(
    client="default_client",
    reranker_entity="RRF",
    reranker_fact="RRF",
    limit_vector_results=15,
    alpha_hybrid=0.6,
    limit_fact=30,
    limit_entity=10,
    k = 2
    )

    kpi_qualitative_speedboat = QualitativeKPIs_speedboat(client=company)
    query_qualitative_speedboat_list = kpi_qualitative_speedboat.all_queries_list()

    kpi_quantitative = QUANTITATIVE_KPIs_speedboat(client=company)
    if company == "Walmart":
        query_quantitative_speedboat_list = kpi_quantitative.all_queries_list(year_basis="FY", year_0 = 2025, year_1= 2024, year_2=2023)
    elif company == "RWE":
        query_quantitative_speedboat_list = kpi_quantitative.all_queries_list(year_basis="FY", year_0 = 2024, year_1= 2023, year_2=2022)

    query_complete = query_qualitative_speedboat_list + query_quantitative_speedboat_list


    manager = create_credit_risk_report()



    await manager.run(client=company, agent_info=agent_info, query_list=query_complete, description="Full Report")


    await close_graph()
    close_database()
    logger.info("Graph and vector database connections closed")



    



if __name__ == "__main__":
    asyncio.run(main())



