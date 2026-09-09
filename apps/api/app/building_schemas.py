from typing import Literal

from pydantic import BaseModel, Field

from .registry_schemas import ExtractionMethod, ReviewItem, SourceEvidence


class BuildingMetadata(BaseModel):
    document_type: Literal["building_ledger"] = "building_ledger"
    ledger_type: Literal["general", "collective_title", "collective_unit", "unknown"]
    pages: int = Field(ge=1)


class BuildingProperty(BaseModel):
    lot_address: str | None = None
    road_address: str | None = None
    building_name: str | None = None
    unit: str | None = None
    floor: int | None = None
    exclusive_area: float | None = Field(default=None, gt=0)
    main_use: str | None = None
    structure: str | None = None
    households: int | None = Field(default=None, ge=0)
    approval_date: str | None = None
    is_illegal_building: bool | None = None


class BuildingLedgerExtraction(BaseModel):
    document: BuildingMetadata
    property: BuildingProperty
    evidence: dict[str, SourceEvidence]
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = []
    needs_review: list[ReviewItem] = []

