from __future__ import annotations

from uuid import uuid4

from ..building_schemas import BuildingLedgerExtraction
from ..lease_schemas import LeaseContractExtraction
from ..registry_schemas import RegistryExtraction
from ..risk_engine import analyze_risk
from ..schemas import (
    AIExplanation,
    AnalysisResponse,
    CheckItem,
    ExtractedFacts,
    MarketDataState,
)
from .cross_checker import cross_check_documents


def _approval_year(ledger: BuildingLedgerExtraction) -> int | None:
    value = ledger.property.approval_date
    if not value or len(value) < 4 or not value[:4].isdigit():
        return None
    return int(value[:4])


def _bundle_checks(bundle) -> list[CheckItem]:
    status_map = {
        "verified": "verified",
        "mismatch": "warning",
        "needs_review": "needs_review",
    }
    checks = [
        CheckItem(label=item.label, status=status_map[item.status], detail=item.detail)
        for item in bundle.cross_checks
    ]
    checks.append(
        CheckItem(
            label="보증보험 가입",
            status="needs_review",
            detail="보증기관에서 추가 확인이 필요합니다",
        )
    )
    return checks


def build_analysis(
    *,
    address: str,
    deposit: int,
    monthly_rent: int,
    registry: RegistryExtraction,
    building_ledger: BuildingLedgerExtraction,
    lease_contract: LeaseContractExtraction,
) -> AnalysisResponse:
    bundle = cross_check_documents(
        registry,
        building_ledger,
        lease_contract,
        input_address=address,
        input_deposit=deposit,
        input_monthly_rent=monthly_rent,
    )
    owner = registry.ownership[0].owner_name if registry.ownership else None
    landlord = next(
        (party.name for party in lease_contract.parties if party.role == "landlord"),
        None,
    )
    mortgage_amount = sum(
        entry.maximum_claim_amount or 0
        for entry in registry.encumbrances
        if entry.status == "active" and entry.right_type == "mortgage"
    )
    facts = ExtractedFacts(
        owner=owner,
        contract_owner=landlord,
        mortgage_amount=mortgage_amount,
        deposit=deposit,
        estimated_value=None,
        building_use=building_ledger.property.main_use,
        is_illegal_building=building_ledger.property.is_illegal_building,
        approval_year=_approval_year(building_ledger),
        recent_transactions=None,
        local_price_volatility=None,
    )
    risk = analyze_risk(facts)
    document_reviews = (
        registry.needs_review
        + building_ledger.needs_review
        + lease_contract.needs_review
    )
    has_blocking_review = any(item.severity == "blocking" for item in document_reviews)
    has_mismatch = any(item.status == "mismatch" for item in bundle.cross_checks)
    status = "needs_review" if has_blocking_review or has_mismatch else "partial"

    return AnalysisResponse(
        analysis_id=str(uuid4()),
        status=status,
        score=risk.score,
        grade=risk.grade,  # type: ignore[arg-type]
        headline=risk.headline,
        summary=risk.summary,
        facts=facts,
        signals=risk.signals,
        checks=_bundle_checks(bundle),
        actions=risk.actions,
        market_data=MarketDataState(
            status="not_connected",
            message="공공 실거래가 연동 전이라 예상 주택가액과 시세 비율을 계산하지 않았습니다.",
        ),
        ai_explanation=AIExplanation(
            status="disabled",
            provider="gemini",
            model="gemini-3.5-flash-lite",
            message="AI 설명 생성 전입니다.",
        ),
        documents=bundle,
        disclaimer="이 결과는 계약 의사결정을 돕는 참고 정보이며 법률 자문이나 보증 가입 심사를 대신하지 않습니다.",
    )
