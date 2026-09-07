import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .risk_engine import analyze_risk
from .schemas import AnalysisResponse, ExtractedFacts

app = FastAPI(
    title="RentGuard AI API",
    description="전세계약 문서 교차검증 및 위험 분석 API",
    version="0.1.0",
)

origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/api/v1/analyses", response_model=AnalysisResponse)
async def create_analysis(
    address: Annotated[str, Form(min_length=5)],
    deposit: Annotated[int, Form(gt=0)],
    monthly_rent: Annotated[int, Form(ge=0)],
    registry: Annotated[UploadFile | None, File()] = None,
    building_ledger: Annotated[UploadFile | None, File()] = None,
    lease_contract: Annotated[UploadFile | None, File()] = None,
) -> AnalysisResponse:
    # The MVP keeps a stable no-key demo at the same boundary where OCR and
    # public-data adapters will be connected next.
    del address, monthly_rent, registry, building_ledger, lease_contract
    facts = ExtractedFacts(
        owner="김민준",
        contract_owner="김민준",
        mortgage_amount=110_000_000,
        deposit=deposit,
        estimated_value=220_000_000,
        building_use="다세대주택",
        is_illegal_building=False,
        approval_year=2017,
        recent_transactions=3,
        local_price_volatility=.08,
    )
    result = analyze_risk(facts)
    return AnalysisResponse(
        analysis_id=str(uuid4()),
        score=result.score,
        grade=result.grade,  # type: ignore[arg-type]
        headline=result.headline,
        summary=result.summary,
        facts=facts,
        signals=result.signals,
        checks=result.checks,
        actions=result.actions,
        disclaimer="이 결과는 계약 의사결정을 돕는 참고 정보이며 법률 자문이나 보증 가입 심사를 대신하지 않습니다.",
    )
