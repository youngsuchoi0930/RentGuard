from typing import Literal

from pydantic import BaseModel, Field

from .registry_schemas import ExtractionMethod, ReviewItem, SourceEvidence


class ContractMetadata(BaseModel):
    document_type: Literal["lease_contract"] = "lease_contract"
    contract_type: Literal["jeonse", "monthly_with_deposit", "monthly", "unknown"]
    signed_at: str | None = None
    pages: int = Field(ge=1)


class ContractProperty(BaseModel):
    address: str | None = None
    building_description: str | None = None
    leased_part: str | None = None


class ContractParty(BaseModel):
    role: Literal["landlord", "tenant", "agent"]
    name: str
    evidence: SourceEvidence


class ContractMoney(BaseModel):
    value: int | None = Field(default=None, ge=0)
    evidence: SourceEvidence | None = None


class LeasePeriod(BaseModel):
    start: str | None = None
    end: str | None = None
    evidence: SourceEvidence | None = None


class SpecialTerm(BaseModel):
    order: int | None = None
    content: str
    evidence: SourceEvidence


class LeaseContractExtraction(BaseModel):
    document: ContractMetadata
    property: ContractProperty
    parties: list[ContractParty]
    deposit: ContractMoney
    contract_payment: ContractMoney
    balance: ContractMoney
    monthly_rent: ContractMoney
    lease_period: LeasePeriod
    special_terms: list[SpecialTerm]
    extraction_method: ExtractionMethod
    confidence: float = Field(ge=0, le=1)
    warnings: list[str] = []
    needs_review: list[ReviewItem] = []

