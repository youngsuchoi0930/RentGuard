import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .risk_engine import analyze_risk
from .building_schemas import BuildingLedgerExtraction
from .cross_check_schemas import DocumentBundleExtraction
from .lease_schemas import LeaseContractExtraction
from .registry_schemas import RegistryExtraction
from .schemas import AnalysisResponse, ExtractedFacts
from .services.building_parser import extract_building_ledger
from .services.cross_checker import cross_check_documents
from .services.lease_parser import extract_lease_contract
from .services.registry_parser import extract_registry

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


@app.post("/api/v1/documents/registry/extract", response_model=RegistryExtraction)
async def extract_registry_document(
    file: Annotated[UploadFile, File(description="부동산 등기사항증명서 PDF")],
) -> RegistryExtraction:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="PDF 파일만 분석할 수 있습니다.")
    return extract_registry(await file.read())


@app.post("/api/v1/documents/lease-contract/extract", response_model=LeaseContractExtraction)
async def extract_lease_contract_document(
    file: Annotated[UploadFile, File(description="주택임대차계약서 PDF")],
) -> LeaseContractExtraction:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="PDF 파일만 분석할 수 있습니다.")
    return extract_lease_contract(await file.read())


@app.post("/api/v1/documents/building-ledger/extract", response_model=BuildingLedgerExtraction)
async def extract_building_ledger_document(
    file: Annotated[UploadFile, File(description="건축물대장 PDF")],
) -> BuildingLedgerExtraction:
    if file.content_type not in {"application/pdf", "application/octet-stream"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="PDF 파일만 분석할 수 있습니다.")
    return extract_building_ledger(await file.read())


@app.post("/api/v1/document-bundles/extract", response_model=DocumentBundleExtraction)
async def extract_document_bundle(
    address: Annotated[str, Form(min_length=5)],
    deposit: Annotated[int, Form(gt=0)],
    monthly_rent: Annotated[int, Form(ge=0)],
    registry: Annotated[UploadFile, File(description="등기사항증명서 PDF")],
    building_ledger: Annotated[UploadFile, File(description="건축물대장 PDF")],
    lease_contract: Annotated[UploadFile, File(description="주택임대차계약서 PDF")],
) -> DocumentBundleExtraction:
    uploads = (registry, building_ledger, lease_contract)
    if any(upload.content_type not in {"application/pdf", "application/octet-stream"} for upload in uploads):
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="세 문서 모두 PDF 파일이어야 합니다.")
    registry_result = extract_registry(await registry.read())
    ledger_result = extract_building_ledger(await building_ledger.read())
    contract_result = extract_lease_contract(await lease_contract.read())
    return cross_check_documents(
        registry_result,
        ledger_result,
        contract_result,
        input_address=address,
        input_deposit=deposit,
        input_monthly_rent=monthly_rent,
    )


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
