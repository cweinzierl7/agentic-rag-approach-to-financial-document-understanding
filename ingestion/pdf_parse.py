
''' PDF PARSING with LLamaParse'''


from dotenv import load_dotenv
import os
from pathlib import Path
import nest_asyncio
import logging
from llama_cloud_services import LlamaParse
import json
from pathlib import Path

# Load environment variables
load_dotenv()
logger = logging.getLogger(__name__)


def _resolve_pdf_to_ingest_dir(data_dir: str) -> Path:
    """Resolve pdf input directory robustly across different notebook CWDs."""
    requested = Path(data_dir)
    if requested.is_dir():
        return requested.resolve()

    cwd = Path.cwd().resolve()
    candidates: list[Path] = []
    # 1) As given, relative to cwd
    candidates.append((cwd / requested).resolve())
    # 2) Common repo layout: <root>/ingestion/pdf_to_ingest
    candidates.append((cwd / "ingestion" / "pdf_to_ingest").resolve())
    # 3) If cwd is <root>/ingestion/ipynb: ../pdf_to_ingest
    candidates.append((cwd.parent / "pdf_to_ingest").resolve())

    # 4) Walk up parents and try <base>/ingestion/pdf_to_ingest and <base>/pdf_to_ingest
    for base in (cwd,) + tuple(cwd.parents):
        candidates.append((base / "ingestion" / "pdf_to_ingest").resolve())
        candidates.append((base / "pdf_to_ingest").resolve())

    for p in candidates:
        if p.is_dir():
            return p

    tried = "\n".join(f"- {p}" for p in candidates)
    raise FileNotFoundError(
        f"Could not find pdf input dir. Requested='{data_dir}'. Tried:\n{tried}"
    )


class pdf_parser:
    def __init__(self, data_dir: str = "./pdf_to_ingest"):
        # Resolve directory first (so _get_data_files doesn't depend on notebook CWD)
        self.data_dir = str(_resolve_pdf_to_ingest_dir(data_dir))

        # with page agent
        self.parser_page_agent = LlamaParse(
            api_key=os.getenv("PDF_PARSE_API_KEY", ""),
            parse_mode="parse_page_with_agent",
            num_workers=4,
            verbose=True,
            language="en",
            extract_layout=True,
            result_type="markdown",
            adaptive_long_table=True,
            outlined_table_extraction=True,
        )

    def _get_data_files(self) -> list[str]:
        data_path = Path(self.data_dir)
        if not data_path.is_dir():
            raise FileNotFoundError(f"Data dir not found: {data_path}")
        files: list[str] = []
        for f in os.listdir(data_path):
            fname = data_path / f
            if fname.is_file():
                files.append(str(fname))
        return files

    def parse_pdfs(self) -> None:
        nest_asyncio.apply()
        files = self._get_data_files()
        md_json_objs = self.parser_page_agent.get_json_result(files)
        self._write_json_to_ingest(obj=md_json_objs)

    def _write_json_to_ingest(self, obj) -> None:
        """Write a JSON-serializable object into the 'json_to_ingest' folder."""
        # Prefer existing folder if it already exists; otherwise create under ingestion/json_to_ingest
        candidates = [
            Path("json_to_ingest"),
            Path("ingestion") / "json_to_ingest",
            Path("..") / "json_to_ingest",
            Path("..") / "ingestion" / "json_to_ingest",
        ]
        out_dir = next((p for p in candidates if p.is_dir()), Path("ingestion") / "json_to_ingest")
        out_dir.mkdir(parents=True, exist_ok=True)


        for i in obj:
            name = Path(i["file_path"]).stem if "file_path" in i else "PLEASE_SET_NAME_MANUALLY"
            name_save = f"{name}.json"

            out_path = out_dir / name_save
            with out_path.open("w", encoding="utf-8") as f:
                json.dump(i, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # expect pdfs in ./pdf_to_ingest folder

    # Create parser instance
    parser = pdf_parser()

    # Parse PDFs and write to json_to_ingest
    parser.parse_pdfs()