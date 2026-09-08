import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .building_schemas import BuildingLedgerExtraction
from .cross_check_schemas import DocumentBundleExtraction
from .lease_schemas import LeaseContractExtraction
from .registry_schemas import RegistryExtraction
from .schemas import AnalysisResponse
from .services.analysis_service import build_analysis
from .services.building_parser import extract_building_ledger
from .services.cross_checker import cross_check_documents
from .services.lease_parser import extract_lease_contract
from .services.llm_explainer import generate_gemini_explanation
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
    registry: Annotated[UploadFile, File(description="등기사항증명서 PDF")],
    building_ledger: Annotated[UploadFile, File(description="건축물대장 PDF")],
    lease_contract: Annotated[UploadFile, File(description="주택임대차계약서 PDF")],
) -> AnalysisResponse:
    uploads = (registry, building_ledger, lease_contract)
    if any(upload.content_type not in {"application/pdf", "application/octet-stream"} for upload in uploads):
        from fastapi import HTTPException
        raise HTTPException(status_code=415, detail="세 문서 모두 PDF 파일이어야 합니다.")

    registry_bytes = await registry.read()
    ledger_bytes = await building_ledger.read()
    contract_bytes = await lease_contract.read()
    registry_result = await run_in_threadpool(extract_registry, registry_bytes)
    ledger_result = await run_in_threadpool(extract_building_ledger, ledger_bytes)
    contract_result = await run_in_threadpool(extract_lease_contract, contract_bytes)
    analysis = build_analysis(
        address=address,
        deposit=deposit,
        monthly_rent=monthly_rent,
        registry=registry_result,
        building_ledger=ledger_result,
        lease_contract=contract_result,
    )
    analysis.ai_explanation = await generate_gemini_explanation(
        grade=analysis.grade,
        signals=analysis.signals,
        checks=analysis.checks,
        market_data=analysis.market_data,
    )
    return analysis
