from typing import Literal

from pydantic import BaseModel, Field

from .cross_check_schemas import DocumentBundleExtraction


class ExtractedFacts(BaseModel):
    owner: str | None = None
    contract_owner: str | None = None
    mortgage_amount: int = Field(ge=0)
    deposit: int = Field(ge=0)
    estimated_value: int | None = Field(default=None, gt=0)
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


class CheckItem(BaseModel):
    label: str
    status: Literal["verified", "warning", "needs_review"]
    detail: str


class MarketDataState(BaseModel):
    status: Literal["not_connected", "available"]
    message: str


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
    ai_explanation: AIExplanation
    documents: DocumentBundleExtraction
    disclaimer: str
