import os
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from .building_schemas import BuildingLedgerExtraction
from .cross_check_schemas import DocumentBundleExtraction
from .lease_schemas import LeaseContractExtraction
from .registry_schemas import RegistryExtraction
from .schemas import AddressSearchResponse, AnalysisFromExtractionsRequest, AnalysisResponse
from .services.analysis_service import build_analysis
from .services.building_parser import extract_building_ledger
from .services.cross_checker import cross_check_documents
from .services.lease_parser import extract_lease_contract
from .services.llm_explainer import generate_gemini_explanation
from .services.public_data import PublicAPIError, fetch_public_data, search_addresses
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


@app.get("/api/v1/addresses/search", response_model=AddressSearchResponse)
async def search_road_addresses(
    keyword: Annotated[str, Query(min_length=2, max_length=100)],
) -> AddressSearchResponse:
    try:
        return AddressSearchResponse(items=await search_addresses(keyword, limit=10))
    except PublicAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
    analysis_mode: Annotated[Literal["precheck", "contract_review"], Form()] = "contract_review",
    lease_contract: Annotated[
        UploadFile | None,
        File(description="계약서 교차검증 모드에서 필요한 주택임대차계약서 PDF"),
    ] = None,
) -> DocumentBundleExtraction:
    if analysis_mode == "contract_review" and lease_contract is None:
        raise HTTPException(status_code=422, detail="계약서 교차검증 모드에는 임대차계약서가 필요합니다.")
    uploads = [registry, building_ledger]
    if analysis_mode == "contract_review" and lease_contract:
        uploads.append(lease_contract)
    if any(upload.content_type not in {"application/pdf", "application/octet-stream"} for upload in uploads):
        raise HTTPException(status_code=415, detail="업로드 문서는 모두 PDF 파일이어야 합니다.")
    registry_result = await run_in_threadpool(extract_registry, await registry.read())
    ledger_result = await run_in_threadpool(extract_building_ledger, await building_ledger.read())
    contract_result = None
    if analysis_mode == "contract_review" and lease_contract:
        contract_result = await run_in_threadpool(extract_lease_contract, await lease_contract.read())
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
    analysis_mode: Annotated[Literal["precheck", "contract_review"], Form()] = "contract_review",
    lease_contract: Annotated[
        UploadFile | None,
        File(description="계약서 교차검증 모드에서 필요한 주택임대차계약서 PDF"),
    ] = None,
) -> AnalysisResponse:
    if analysis_mode == "contract_review" and lease_contract is None:
        raise HTTPException(status_code=422, detail="계약서 교차검증 모드에는 임대차계약서가 필요합니다.")

    uploads = [registry, building_ledger]
    if analysis_mode == "contract_review" and lease_contract:
        uploads.append(lease_contract)
    if any(upload.content_type not in {"application/pdf", "application/octet-stream"} for upload in uploads):
        raise HTTPException(status_code=415, detail="업로드 문서는 모두 PDF 파일이어야 합니다.")

    registry_bytes = await registry.read()
    ledger_bytes = await building_ledger.read()
    registry_result = await run_in_threadpool(extract_registry, registry_bytes)
    ledger_result = await run_in_threadpool(extract_building_ledger, ledger_bytes)
    contract_result = None
    if analysis_mode == "contract_review" and lease_contract:
        contract_result = await run_in_threadpool(extract_lease_contract, await lease_contract.read())
    analysis = build_analysis(
        address=address,
        deposit=deposit,
        monthly_rent=monthly_rent,
        registry=registry_result,
        building_ledger=ledger_result,
        lease_contract=contract_result,
        mode=analysis_mode,
        public_data=await fetch_public_data(address),
    )
    analysis.ai_explanation = await generate_gemini_explanation(
        grade=analysis.grade,
        signals=analysis.signals,
        checks=analysis.checks,
        market_data=analysis.market_data,
    )
    return analysis


@app.post("/api/v1/analyses/from-extractions", response_model=AnalysisResponse)
async def create_analysis_from_extractions(
    payload: AnalysisFromExtractionsRequest,
) -> AnalysisResponse:
    lease_contract = (
        payload.documents.lease_contract
        if payload.mode == "contract_review"
        else None
    )
    if payload.mode == "contract_review" and lease_contract is None:
        raise HTTPException(status_code=422, detail="계약서 교차검증 모드에는 임대차계약서가 필요합니다.")

    analysis = build_analysis(
        address=payload.address,
        deposit=payload.deposit,
        monthly_rent=payload.monthly_rent,
        registry=payload.documents.registry,
        building_ledger=payload.documents.building_ledger,
        lease_contract=lease_contract,
        mode=payload.mode,
        public_data=await fetch_public_data(payload.address),
        corrections=payload.corrections,
    )
    analysis.ai_explanation = await generate_gemini_explanation(
        grade=analysis.grade,
        signals=analysis.signals,
        checks=analysis.checks,
        market_data=analysis.market_data,
    )
    return analysis
