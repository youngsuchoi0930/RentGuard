from typing import Literal

from pydantic import BaseModel, Field


ExtractionMethod = Literal["pdf_text", "ocr"]
ReviewSeverity = Literal["info", "warning", "blocking"]


class SourceEvidence(BaseModel):
    page: int = Field(ge=1)
    section: Literal[
        "document",
        "title",
        "registry_a",
        "registry_b",
        "contract_property",
        "contract_terms",
        "contract_special_terms",
        "contract_parties",
        "ledger_overview",
        "ledger_floors",
    ]
    raw_text: str
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)


class ReviewItem(BaseModel):
    code: str
    severity: ReviewSeverity
    message: str


class RegistryMetadata(BaseModel):
    document_type: Literal["real_estate_registry"] = "real_estate_registry"
    certificate_type: Literal[
        "full_with_cancelled",
        "full_current",
        "partial_specific_share",
        "partial_current_owners",
        "partial_share_history",
        "unknown",
    ]
    property_type: Literal["land", "building", "condominium", "unknown"]
    issued_at: str | None = None
    pages: int = Field(ge=1)


class RegistryProperty(BaseModel):
    lot_address: str | None = None
    road_address: str | None = None
    building_name: str | None = None
    unit: str | None = None


class OwnershipEntry(BaseModel):
    rank: str | None = None
    owner_name: str
    share: str | None = None
    status: Literal["active", "cancelled", "unknown"] = "active"
    registered_at: str | None = None
    evidence: SourceEvidence | None = None


class EncumbranceEntry(BaseModel):
    rank: str | None = None
    right_type: Literal[
        "mortgage",
        "seizure",
        "provisional_seizure",
        "trust",
        "leasehold",
        "other",
    ]
    maximum_claim_amount: int | None = Field(default=None, ge=0)
    holder: str | None = None
    debtor: str | None = None
    status: Literal["active", "cancelled", "unknown"] = "active"
    registered_at: str | None = None
    evidence: SourceEvidence | None = None


class RegistryExtraction(BaseModel):
    document: RegistryMetadata
    property: RegistryProperty
    evidence: dict[str, SourceEvidence] = Field(default_factory=dict)
    ownership: list[OwnershipEntry]
    encumbrances: list[EncumbranceEntry]
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = []
    needs_review: list[ReviewItem] = []


class FieldComparison(BaseModel):
    field: str
    expected: str | int | bool | None
    actual: str | int | bool | None
    passed: bool


class RegistryEvaluation(BaseModel):
    passed: bool
    matched: int
    total: int
    accuracy: float
    comparisons: list[FieldComparison]
