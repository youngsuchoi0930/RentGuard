from typing import Literal

from pydantic import BaseModel, Field

from .cross_check_schemas import DocumentBundleExtraction


class UserCorrection(BaseModel):
    field: str = Field(min_length=3, max_length=120)
    label: str = Field(min_length=1, max_length=80)
    previous_value: str | int | bool | None = None
    corrected_value: str | int | bool | None = None


class EvidenceReference(BaseModel):
    document: Literal["registry", "building_ledger", "lease_contract"]
    field: str
    label: str
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    raw_text: str | None = None
    extraction_method: Literal["pdf_text", "ocr"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    corrected: bool = False
    previous_value: str | int | bool | None = None
    corrected_value: str | int | bool | None = None


class ExtractedFacts(BaseModel):
    owner: str | None = None
    contract_owner: str | None = None
    mortgage_amount: int = Field(ge=0)
    deposit: int = Field(ge=0)
    monthly_rent: int = Field(default=0, ge=0)
    estimated_value: int | None = Field(default=None, gt=0)
    estimated_value_low: int | None = Field(default=None, gt=0)
    estimated_value_high: int | None = Field(default=None, gt=0)
    building_use: str | None = None
    is_illegal_building: bool | None = None
    approval_year: int | None = None
    recent_transactions: int | None = Field(default=None, ge=0)
    local_price_volatility: float | None = Field(default=None, ge=0)


class RiskSignal(BaseModel):
    id: str
    severity: Literal["safe", "notice", "warning", "danger"]
    title: str
    description: str
    evidence: str
    points: int
    sources: list[EvidenceReference] = Field(default_factory=list)


class CheckItem(BaseModel):
    label: str
    status: Literal["verified", "warning", "needs_review"]
    detail: str
    sources: list[EvidenceReference] = Field(default_factory=list)


class MarketDataState(BaseModel):
    status: Literal["not_connected", "available", "unavailable"]
    message: str
    source: str | None = None
    method: str | None = None
    as_of: str | None = None


class DepositMarketState(BaseModel):
    status: Literal["available", "unavailable", "out_of_scope"]
    message: str
    expected_deposit: int | None = Field(default=None, ge=0)
    upper_deposit: int | None = Field(default=None, ge=0)
    upper_ratio: float | None = Field(default=None, ge=0)
    exceeds_upper: bool | None = None
    source: str = "국토교통부 연립·다세대 전월세 신고자료"
    model_version: str | None = None
    training_period_end: str | None = None


class AddressSuggestion(BaseModel):
    road_address: str
    jibun_address: str
    zip_code: str
    building_name: str | None = None


class AddressSearchResponse(BaseModel):
    items: list[AddressSuggestion]


class AIExplanation(BaseModel):
    status: Literal["generated", "unavailable", "disabled"]
    provider: Literal["gemini"]
    model: str
    overview: str | None = None
    caution: str | None = None
    limitation: str | None = None
    privacy_note: str | None = None
    message: str | None = None


class AnalysisResponse(BaseModel):
    analysis_id: str
    mode: Literal["precheck", "contract_review"]
    status: Literal["complete", "partial", "needs_review"]
    score: int = Field(ge=0, le=100)
    grade: Literal["낮음", "주의", "높음"]
    headline: str
    summary: str
    facts: ExtractedFacts
    signals: list[RiskSignal]
    checks: list[CheckItem]
    actions: list[str]
    market_data: MarketDataState
    deposit_market: DepositMarketState
    ai_explanation: AIExplanation
    documents: DocumentBundleExtraction
    corrections: list[UserCorrection] = Field(default_factory=list)
    disclaimer: str


class AnalysisFromExtractionsRequest(BaseModel):
    mode: Literal["precheck", "contract_review"]
    address: str = Field(min_length=5, max_length=200)
    deposit: int = Field(gt=0)
    monthly_rent: int = Field(ge=0)
    documents: DocumentBundleExtraction
    corrections: list[UserCorrection] = Field(default_factory=list, max_length=50)
