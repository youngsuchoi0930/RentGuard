from typing import Literal

from pydantic import BaseModel, Field


class ExtractedFacts(BaseModel):
    owner: str
    contract_owner: str
    mortgage_amount: int = Field(ge=0)
    deposit: int = Field(ge=0)
    estimated_value: int = Field(gt=0)
    building_use: str
    is_illegal_building: bool
    approval_year: int
    recent_transactions: int = Field(ge=0)
    local_price_volatility: float = Field(ge=0)


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


class AnalysisResponse(BaseModel):
    analysis_id: str
    score: int = Field(ge=0, le=100)
    grade: Literal["낮음", "주의", "높음"]
    headline: str
    summary: str
    facts: ExtractedFacts
    signals: list[RiskSignal]
    checks: list[CheckItem]
    actions: list[str]
    disclaimer: str
