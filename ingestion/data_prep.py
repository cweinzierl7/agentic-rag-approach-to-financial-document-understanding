""" 
Markdown preparation and cleaning functions. + Item and Table preparation classes.
"""



import os
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
from pathlib import Path
import unicodedata
from dataclasses import dataclass, field
import re
import copy
from copy import deepcopy
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI


from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

import os

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class MarkdownPrep:
    """
    A class for preparing and cleaning markdown JSON objects.
    Adds metadata, normalizes text, and removes headers/footers.
    """
    def __init__(self, client: str = "default_client"):
        self.client = client


    def markdown_prep(self, md_json_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        md_json_objs_meta = self._json_item_metadata(md_json_objs)
        md_json_objs_clean = self._header_footer_removal(md_json_objs_meta)
        return md_json_objs_clean

    def markdown_full_doc(self, md_json_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Combines all pages of each document into a single markdown string.
        """
        full_docs = []

        for obj in self.markdown_prep(md_json_objs):
            title = self._extract_title(obj)
            file_path = obj.get("file_path", "unknown")
            full_md = "\n\n".join(page.get("md", "") for page in obj.get("pages", []))
            client = self.client

            full_docs.append({
                "title": title,
                "file_path": file_path,
                "full_markdown": full_md,
                "client": client
            })

        def _safe_filename(value: str, max_len: int = 120) -> str:
            value = self._normalize_spaces(value or "Untitled")
            # Replace characters that are problematic on macOS/Windows filesystems
            value = re.sub(r"[\\/:*?\"<>|]", "_", value)
            value = re.sub(r"\s+", " ", value).strip()
            if len(value) > max_len:
                value = value[:max_len].rstrip()
            return value or "Untitled"

        # Ensure the output directory exists (relative to project root)
        project_root = Path(__file__).resolve().parents[1]
        output_dir = project_root / "markdowns" / "md_documents" / f"documents_prepared_{self.client}_md"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save each combined markdown document
        for idx, doc in enumerate(full_docs):
            title_safe = _safe_filename(str(doc.get("title", "Untitled")))
            file_path_save = output_dir / f"{self.client}_doc{idx}_{title_safe}.md"

            header = (
                f"# {doc.get('title', 'Untitled')}\n\n"
                f"- client: {doc.get('client', '')}\n"
                f"- source_file: {doc.get('file_path', '')}\n\n"
                "---\n\n"
            )
            body = doc.get("full_markdown", "")
            if not isinstance(body, str):
                body = json.dumps(body, ensure_ascii=False, indent=2)

            with open(file_path_save, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(body)

        return full_docs

    def title_list(self, md_json_objs: List[Dict[str, Any]]) -> List[str]:
        titles = []
        if not md_json_objs:
            return titles
        for i, obj in enumerate(md_json_objs):
            title = self._extract_title(obj)
            if title:
                titles.append(title)
        return titles   

    def _json_item_metadata(self, md_json_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:

        for obj in md_json_objs:
            title = self._extract_title(obj)
            file_path = obj.get("file_path", "unknown")
            if self.client:
                obj["client"] = self.client

            for page in obj.get("pages", []):
                page["file_path"] = file_path

                for item in page.get("items", []):
                    item["page"] = page.get("page")
                    item["file_path_org"] = file_path
                    item["title"] = title
                    if self.client:
                        item["client"] = self.client

        return md_json_objs

    def _normalize_spaces(self, s: str) -> str:
        """Normalize odd whitespace/invisible characters to single ASCII spaces."""
        if not s:
            return ""
        # Remove zero-width, BOM, or format characters
        for z in ('\u200b', '\u200c', '\u200d', '\ufeff', '\u2060'):
            s = s.replace(z, "")
        # Convert unicode spaces to ASCII space
        s = "".join(" " if (c.isspace() or unicodedata.category(c).startswith("Z")) else c for c in s)
        # Collapse runs of spaces
        return re.sub(r" +", " ", s).strip()

    def _extract_title(self, content: Dict[str, Any]) -> str:
        """Extracts the title from the first page's headings, or falls back to first item."""
        title = ""
        items = content.get("pages", [{}])[0].get("items", [])

        for item in items:
            if item.get("type") == "heading":
                text = self._normalize_spaces(item.get("value", ""))
                title = f"{title} - {text}" if title else text

        if title:
            return title

        try:
            return self._normalize_spaces(items[0].get("value", ""))
        except Exception:
            return "Untitled"

    def _match_header_pattern(self, header: str) -> bool:
        """Return True if header matches known header patterns."""
        header_patterns = [
            r"^\d+\s*\|\s*.+",                 # number | text
            r"^\d+\s+[A-Za-z].+",              # number text
            r"^\d+$",                          # only number
            r".*\|\s*\d+$",                    # ends with | number
            r"^\d+\s+\d+(?:\s+\d+)*\s+.*$",    # multiple numbers followed by text
        ]
        return any(re.match(p, header.strip()) for p in header_patterns)

    def _simple_header_clean(self, md_json_objs_page: Dict[str, Any]) -> Dict[str, Any]:
        """
        Relabels text items as headers when they match header patterns,
        but stops when a pure page number or multi-number line is encountered.
        """
        header_candidate = []
        last_header_item = None
        items = md_json_objs_page.get("items", [])

        for item in items:
            md_text = item.get("md", "")

            # stop collecting if this is just a page number like "09" or a line with multiple numbers
            if re.match(r"^\s*\d+\s*$", md_text) or re.match(
                r"^\d+\s+\d+(?:\s+\d+)*\s+.*$",
                self._normalize_spaces(items[0].get("md", "")),
            ):
                last_header_item = item
                break

            if item.get("type") == "text":
                header_candidate.append(item)

        if last_header_item:
            header_candidate.append(last_header_item)

        # After the loop, test combined header text
        if header_candidate:
            combined = " ".join(i.get("md", "") for i in header_candidate).strip()
            if self._match_header_pattern(self._normalize_spaces(combined)):
                for i in header_candidate:
                    i["type"] = "header"

        return md_json_objs_page

    def _header_footer_removal(self, md_json_objs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Removes headers and footers from markdown objects.

        - Uses pageHeaderMarkdown / pageFooterMarkdown if available.
        - Otherwise, attempts detection via _simple_header_clean.
        - Cleans content in both 'md' and 'items'.
        """
        header_count = 0
        footer_count = 0

        any_header = any(
            page.get("pageHeaderMarkdown", "").strip()
            for obj in md_json_objs
            for page in obj.get("pages", [])
        )

        
        any_footer = any(
            page.get("pageFooterMarkdown", "").strip()
            for obj in md_json_objs
            for page in obj.get("pages", [])
        )

        header_recognized = any(
            items["type"] == "header" 
            for obj in md_json_objs
            for page in obj.get("pages", [])
            for items in page.get("items", [])
        )   


        if any_header or any_footer:
            for obj in md_json_objs:
                for page in obj["pages"]:
                    header = page.get("pageHeaderMarkdown", "")
                    footer = page.get("pageFooterMarkdown", "")

                    # Detect headers manually if not already found
                    if not header.strip():
                        page = self._simple_header_clean(page)
                        for item in page["items"]:
                            if item.get("type") == "header":
                                page["md"] = page["md"].replace(item["md"], "")
                                header += " " + item.get("md", "")
                        page["pageHeaderMarkdown"] = header.strip()

                    # Remove header/footer from md text
                    page["md"] = page["md"].replace(header, "").replace(footer, "").strip()

                    # Remove matching items
                    if header:
                        page["items"] = [
                            item
                            for item in page["items"]
                            if item.get("md", "").strip() != header.strip()
                            and item.get("type") != "header"
                        ]

                    # Remove leading header fragments
                    if header:
                        header_stripped = header.strip()
                        new_items = []
                        header_found = False
                        for item in page["items"]:
                            if not header_found and item.get("md", "").strip() in header_stripped:
                                header_count += 1
                                continue
                            header_found = True
                            new_items.append(item)
                        page["items"] = new_items

                    # Remove trailing footer fragments
                    if footer:
                        footer_stripped = footer.strip()
                        while page["items"] and page["items"][-1].get("md", "").strip() in footer_stripped:
                            page["items"].pop()
                            footer_count += 1

        elif header_recognized:
            for obj in md_json_objs:
                for page in obj["pages"]:
                    new_items = []
                    page_md = page["md"]

                    for item in page["items"]:
                        t = item.get("type")
                        if t == "header":
                            page_md = page_md.replace(item.get("md", ""), "").strip()
                        elif t == "footer":
                            page_md = page_md.replace(item.get("md", ""), "").strip()
                        elif t == "image":
                            continue
                        else:
                            new_items.append(item)

                    page["md"] = page_md
                    page["items"] = new_items

        return md_json_objs




@dataclass
class Item:
    type_item: str
    md: str
    value: str
    doc_title: str
    page: int
    item_idx: int
    item_page_idx: int
    number_combined_items: int
    file_path: str
    table_idx: Optional[int] = None
    table_md: Optional[str] = None
    lvl: Optional[int] = None
    heading_lvl1: Optional[str] = None
    heading_lvl2: Optional[str] = None
    heading_lvl3: Optional[str] = None
    client: Optional[str] = None


class ItemPrep:
    """A class for preparing and cleaning markdown items.
    Adds heading levels to items based on their type. """

    def create_items(self, md_json_objs: List[Dict[str, Any]]) -> List[Item]:
        item_list = []
        idx_global = 0
        for doc in md_json_objs:
            for page in doc.get("pages", []):
                for idx, item in enumerate(page.get("items", [])):
                    item_list.append(Item(
                        type_item=item.get("type", ""),
                        md=item.get("md", ""),
                        value=item.get("value", ""),
                        doc_title=self._extract_title(doc),
                        page=item.get("page", ""),
                        item_idx=idx_global,
                        item_page_idx=idx,
                        number_combined_items=1,
                        file_path=item.get("file_path_org", ""),
                        lvl=item.get("lvl", None),
                        client=item.get("client", "default_client")
                    ))
                    idx_global += 1

        item_list = self._heading_levels(item_list)
        item_list = self._item_combine(item_list)
        
        return item_list

    def _heading_levels(self, item_list: List[Item]) -> List[Item]:
        """
        Adds heading levels to items based on their type.
        """

        current_heading_lvl1 = None
        current_heading_lvl2 = None
        current_heading_lvl3 = None
        # current_heading_lvl4 = None

        # Iterate through each item in item_list
        for item in item_list:
            
            if item.type_item == 'heading':
                # If the item is a heading, update the current heading
                if item.lvl == 1:
                    current_heading_lvl1 = item.value
                    current_heading_lvl2 = None
                    current_heading_lvl3 = None

                    item.heading_lvl1 = current_heading_lvl1
                    item.heading_lvl2 = None
                    item.heading_lvl3 = None
        #            current_heading_lvl4 = None


                elif item.lvl  == 2:
                    current_heading_lvl2 = item.value
                    current_heading_lvl3 = None
        #            current_heading_lvl4 = None
                    item.heading_lvl1 = current_heading_lvl1
                    item.heading_lvl2 = current_heading_lvl2
                    item.heading_lvl3 = None



                elif item.lvl == 3:
                    current_heading_lvl3 = item.value
                #     current_heading_lvl4 = None
                    item.heading_lvl1 = current_heading_lvl1
                    item.heading_lvl2 = current_heading_lvl2
                    item.heading_lvl3  = current_heading_lvl3



            elif item.type_item !=  'heading' and current_heading_lvl1 is not None:
                    # If the item is text and there is a current heading, append the text to the last heading's list
                    item.heading_lvl1 = current_heading_lvl1
                    item.heading_lvl2 = current_heading_lvl2
                    item.heading_lvl3 = current_heading_lvl3
        return item_list


    def _item_combine(self, item_list: List[Item]) -> List[Item]:
        """
        Combines consecutive text items into a single item.
        """

        item_chunk_combined = []

        for idx, item in enumerate(item_list):
            
            if not item_chunk_combined:
                # Always add the first item
                item_chunk_combined.append(deepcopy(item))
                continue

            last_item = item_chunk_combined[-1]

            if (
                item.type_item != "table"
                and last_item.type_item != "table"
                and last_item.page == item.page
                and (last_item.heading_lvl1 == item.heading_lvl1)
                and (last_item.heading_lvl2 == None or last_item.heading_lvl2 == item.heading_lvl2)
                and (last_item.heading_lvl3 == None or last_item.heading_lvl3 == item.heading_lvl3)

            ):
                # Merge with last item
                last_item.md += "\n" + item.md
                last_item.value += "\n" + item.value
                last_item.type_item += ", " + item.type_item
                last_item.heading_lvl2 = item.heading_lvl2
                last_item.heading_lvl3 = item.heading_lvl3
                last_item.number_combined_items += 1

                # Decrement item_idx for all items from idx onward
                for item in item_list[idx:]:
                    item.item_idx -= 1  

                # Decrement item_page_idx while still on the same page
                for item in item_list[idx:]:
                    if item.page == last_item.page:
                        item.item_page_idx -= 1


            else:
                # Append new item as is
                item_chunk_combined.append(deepcopy(item))

        # Finally, remove items that are only headings
        item_chunk_combined = self._delete_heading_only_items(item_chunk_combined)
        return item_chunk_combined

    def _extract_title(self, content: list) -> str:
        """
        Extracts the title from the content.

        Takes all headings from the first page and concatenates them with " - ".
        """

        title = ""
        for item in content["pages"][0]["items"]:
            if item["type"] == "heading":
                if title == "":
                    title = self._normalize_spaces(item["value"])
                else: 
                    title = title + " - "+ self._normalize_spaces(item["value"])

        if title != "":
            return title
        else:
            try: return self._normalize_spaces(content["pages"][0]["items"][0]["value"])
            except: return "Untitled"

    def _normalize_spaces(self, s: str) -> str:
            """Normalize odd whitespace/invisible characters to single ASCII spaces."""
            if not s:
                return ""
            # Remove zero-width, BOM, or format characters
            for z in ('\u200b', '\u200c', '\u200d', '\ufeff', '\u2060'):
                s = s.replace(z, "")
            # Convert unicode spaces to ASCII space
            s = "".join(" " if (c.isspace() or unicodedata.category(c).startswith("Z")) else c for c in s)
            # Collapse runs of spaces
            return re.sub(r" +", " ", s).strip()
    

    def _delete_heading_only_items(self, item_list: List[Item]) -> List[Item]:
        """
        Deletes items that are only headings (no associated text).
        """

        cleaned_items = [item for item in item_list if item.type_item != "heading"]
        return cleaned_items
    


""" Tables preparation and summarization class. """

@dataclass
class Table: 
    table_md: str
    table_summary: str
    doc_title: str
    page: int
    item_idx: int
    table_idx: int
    file_path: str


class TablePrep:
    """Extracts tables from markdown JSON objects and summarizes them."""

    data_dir: str = '../markdowns/md_tables/markdown_tables_summary'
    max_concurrency: int = 5
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

    async def create_table_summaries(self, item_list: List[Item]) -> List[Item]:
        # Ensure we always have Item objects
        item_list = [item if isinstance(item, Item) else Item(**item) for item in item_list]

        item_list = await self._define_tables(item_list)
        item_list = await self._create_summaries(item_list)
        self._save_table_summary(item_list)
        return item_list

    async def _define_tables(self, item_list: List[Item]) -> List[Item]:
        if not any(item.type_item == "table" for item in item_list):
            item_list = self._classify_items_table(item_list)

        table_idx = 0
        for item in item_list:
            if item.type_item == 'table':
                item.table_md = item.md
                item.table_idx = table_idx
                table_idx += 1
        logger.info(f"Found {table_idx} tables in the documents.")
        return item_list

    async def _create_summaries(self, item_list: List[Item]) -> List[Item]:
        # prompt_table_summary_text = """You are an assistant tasked with summarizing tables.
        # Give a concise summary of the table. Table: {element} """

        # prompt_table_summary = ChatPromptTemplate.from_template(prompt_table_summary_text)
        # model_summary = ChatOpenAI(temperature=0, model="gpt-4")

        # summarize_chain = {"element": lambda x: x} | prompt_table_summary | model_summary | StrOutputParser()
        async def summarize_table(table):
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You summarize Markdown tables."},
                    {"role": "user", "content": f"You are an assistant tasked with summarizing tables. Give a concise summary of the table. Table: \n\n{table}"}
                ],
                temperature=0
            )
            return response.choices[0].message.content.strip()

        async def process_in_batches(tables, batch_size=self.max_concurrency):
            semaphore = asyncio.Semaphore(batch_size)  # limit concurrent requests

            async def limited_summarize(table, index):
                async with semaphore:
                    summary = await summarize_table(table)
                    logger.info(f"Finished summarizing table {index + 1}/{len(tables)}")
                    return summary

            # gather all results respecting the batch size limit
            tasks = [limited_summarize(t, i) for i, t in enumerate(tables)]
            results = await asyncio.gather(*tasks)
            return results

        tables_md = [item.table_md for item in item_list if item.type_item == 'table' and item.table_md]

        # NOTE: batch is sync – if you want async, replace with abatch + await
        # table_summaries = summarize_chain.batch(tables_md, {"max_concurrency": self.max_concurrency})
        table_summaries = await process_in_batches(tables_md, batch_size=self.max_concurrency)

        logger.info(f"Generated {len(table_summaries)} table summaries.")

        if len(table_summaries) != len(tables_md):
            logger.info("Warning: Number of summaries does not match number of tables.")
        else:
            summary_idx = 0
            for item in item_list:
                if item.type_item == 'table' and item.table_md:
                    item.md = table_summaries[summary_idx]
                    summary_idx += 1
        return item_list

    def _save_table_summary(self, item_list: List[Item]):
        client = item_list[0].client if item_list and getattr(item_list[0], "client", None) else "default_client"

        def _safe_filename(value: str, max_len: int = 120) -> str:
            value = re.sub(r"\s+", " ", (value or "")).strip()
            value = re.sub(r"[\\/:*?\"<>|]", "_", value)
            if len(value) > max_len:
                value = value[:max_len].rstrip()
            return value or "untitled"

        project_root = Path(__file__).resolve().parents[1]
        base_dir = project_root / "markdowns" / "md_tables"
        data_dir_tables_summary = base_dir / f"{client}_tables_summary"
        data_dir_tables = base_dir / f"{client}_tables"

        logger.info(f"Saving table summaries to {data_dir_tables_summary}")
        data_dir_tables_summary.mkdir(parents=True, exist_ok=True)
        data_dir_tables.mkdir(parents=True, exist_ok=True)

        # Save summaries
        for item in item_list:
            if item.type_item != "table":
                continue
            file_stem = _safe_filename(Path(item.file_path).name.replace(".json", ""))
            page = item.page if item.page is not None else 0
            table_idx = (item.table_idx + 1) if item.table_idx is not None else 0
            file_path = data_dir_tables_summary / f"table_summary_{table_idx}_{file_stem}_page{page}.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(item.md or "")

        logger.info(f"Saving tables to {data_dir_tables}")

        # Save raw tables
        for item in item_list:
            if item.type_item != "table":
                continue
            file_stem = _safe_filename(Path(item.file_path).name.replace(".json", ""))
            page = item.page if item.page is not None else 0
            table_idx = (item.table_idx + 1) if item.table_idx is not None else 0
            file_path = data_dir_tables / f"table_{table_idx}_{file_stem}_page{page}.md"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(item.table_md or "")

    def _classify_items_table(self, item_list: List[Item]) -> List[Item]:
        """Classify items as tables if they match markdown table patterns"""
        for item in item_list:
            lines = item.md.splitlines()
            pipe_lines = [ln for ln in lines if ln.startswith("|")]
            if len(pipe_lines) >= 3 and any("---" in ln for ln in pipe_lines):
                item.type_item = "table"
        return item_list
