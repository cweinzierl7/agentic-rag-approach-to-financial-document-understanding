"""
Pydantic models for data validation and serialization.
"""

from typing import List, Dict, Any, Optional, Literal, TypedDict
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict, field_validator
from enum import Enum
from dataclasses import dataclass, field


# Ingestion Models
class IngestionConfig(BaseModel):
    """Configuration for document ingestion."""
    chunk_size: int = Field(default=400, ge=100, le=5000)
    chunk_overlap: int = Field(default=0, ge=0, le=1000)
    max_chunk_size: int = Field(default=2000, ge=300, le=10000)

    chunk_separator: List[str] = Field(
        default_factory=lambda: ["\n\n", "\n", ". ", "?", "!", " ", ""],
        description="Priority order of separators for chunk splitting."
    )

    chunking_method: str = Field(default="recursive")


    
    @field_validator('chunk_overlap')
    @classmethod
    def validate_overlap(cls, v: int, info) -> int:
        """Ensure overlap is less than chunk size."""
        chunk_size = info.data.get('chunk_size', 400)
        if v >= chunk_size:
            raise ValueError(f"Chunk overlap ({v}) must be less than chunk size ({chunk_size})")
        return v
    
class IngestionResult(BaseModel):
    """Result of the ingestion process."""
    created_docs: List[str]
    total_chunks: int
    total_episodes: int
    processing_time_ms: float
    errors_graph: List[str] = Field(default_factory=list)
    errors_vector_db: int



class GraphSearchFactResult(BaseModel):
    """Knowledge graph facts search result model."""
    fact: str
    uuid: str
    episode_uuids: List[str] = Field(default_factory=list)
    document_sources: str
    valid_at: Optional[str] = None
    invalid_at: Optional[str] = None
    source_node_uuid: Optional[str] = None
    target_node_uuid: Optional[str] = None
    score: Optional[float] = None


class GraphSearchEntityResult(BaseModel):
    """Knowledge graph entities search result model."""
    name: str
    uuid: str
    summary: str
    document_sources: str
    score: Optional[float] = None


class GraphSearchCombiResult(BaseModel):
    """Knowledge graph combined (facts and entities) search result model."""
    facts: List[GraphSearchFactResult] = Field(default_factory=list)
    entities: List[GraphSearchEntityResult] = Field(default_factory=list)




class VectorHybridResult(BaseModel):
    title: str
    page: int
    content: str
    score: Optional[float] = None
    table_md: Optional[str] = None
    explain_score: Optional[float] = None

class VectorResult(BaseModel):
    title: str
    page: int
    content: str
    score: Optional[float] = None
    table_md: Optional[str] = None
    explain_score: Optional[str] = None
    distance: Optional[float] = None


@dataclass
class AgentInfo:
    client: str
    reranker_entity: str
    reranker_fact: str
    limit_vector_results: int 
    alpha_hybrid: float
    limit_fact: int
    limit_entity: int
    k: int
    fusion_hybrid: Optional[str] = None

@dataclass
class AgentInfoBasic:
    client: str

class SourceDict(TypedDict):
    document: str
    page: list[int]

# quantity and quality KPI output models for single agent
class KPI_Output(BaseModel):
    kpi: str = Field(description="Name of the KPI, please use the one mentioned in the query")
    year: Optional[int] = Field(default = None, description="Year of the KPI value")
    type: str = Field(description="Type of KPI: 'quantitative' or 'qualitative'")
    value: Optional[str] = Field(default = None, description="Numeric value for quantitative KPIs with unit, e.g., 'EUR 10 million'")
    unit: Optional[str] = Field(default = None, description="Unit of measurement for quantitative KPIs")
    response: Optional[str] = Field(default = None, description="Textual response only for qualitative KPIs")
    notes: Optional[str] = Field(default = None, description="Additional notes or explanations or calculation formulas")
    source: List[SourceDict] = Field(description="document title and page number where the information was found")
    error: Optional[str] = Field(default = None, description="Error message if any issues occurred during retrieval or calculation")


class KPIcalcInputs(TypedDict, total=False):
    revenue: Optional[float | List[float]]
    cogs: Optional[float | List[float]]
    total_assets: Optional[float | List[float]]
    assets_current: Optional[float | List[float]]
    assets_non_current: Optional[float | List[float]]
    total_liabilities: Optional[float | List[float]]
    liabilities_current: Optional[float | List[float]]
    liabilities_non_current: Optional[float | List[float]]
    intangible_assets: Optional[float | List[float]]
    total_cash: Optional[float | List[float]]
    restricted_cash: Optional[float | List[float]]
    ebit: Optional[float | List[float]]
    depreciation_amortization: Optional[float | List[float]]

class KPIcalcRes(TypedDict):
    kpi_name: str
    value: Optional[float]
    formula_used: str
    inputs_received: Dict[str, Optional[float]]
    error: Optional[str]




