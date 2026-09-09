from __future__ import annotations

from typing import Literal
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
from .cross_checker import _address_matches, cross_check_documents
from .public_data import PublicDataResult


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


def _comparable_text(value: str | None) -> str:
    return "".join(character for character in (value or "") if character.isalnum()).lower()


def build_analysis(
    *,
    address: str,
    deposit: int,
    monthly_rent: int,
    registry: RegistryExtraction,
    building_ledger: BuildingLedgerExtraction,
    lease_contract: LeaseContractExtraction | None,
    mode: Literal["precheck", "contract_review"] = "contract_review",
    public_data: PublicDataResult | None = None,
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
    landlord = (
        next((party.name for party in lease_contract.parties if party.role == "landlord"), None)
        if lease_contract
        else None
    )
    mortgage_amount = sum(
        entry.maximum_claim_amount or 0
        for entry in registry.encumbrances
        if entry.status == "active" and entry.right_type == "mortgage"
    )
    market = public_data.market if public_data else None
    official_building = public_data.building if public_data else None
    official_illegal = (
        official_building.is_illegal_building
        if official_building and official_building.status == "available"
        else None
    )
    approval_year = _approval_year(building_ledger)
    if approval_year is None and official_building and official_building.approval_date:
        raw_year = official_building.approval_date[:4]
        approval_year = int(raw_year) if raw_year.isdigit() else None
    facts = ExtractedFacts(
        owner=owner,
        contract_owner=landlord,
        mortgage_amount=mortgage_amount,
        deposit=deposit,
        estimated_value=market.estimated_value if market else None,
        estimated_value_low=market.estimated_value_low if market else None,
        estimated_value_high=market.estimated_value_high if market else None,
        building_use=building_ledger.property.main_use or (
            official_building.main_use if official_building else None
        ),
        is_illegal_building=(
            official_illegal
            if official_illegal is not None
            else building_ledger.property.is_illegal_building
        ),
        approval_year=approval_year,
        recent_transactions=market.transaction_count if market else None,
        local_price_volatility=market.volatility if market else None,
    )
    risk = analyze_risk(facts)
    document_reviews = registry.needs_review + building_ledger.needs_review
    if lease_contract:
        document_reviews += lease_contract.needs_review
    has_blocking_review = any(item.severity == "blocking" for item in document_reviews)
    has_mismatch = any(item.status == "mismatch" for item in bundle.cross_checks)
    has_official_mismatch = False
    checks = _bundle_checks(bundle)
    if official_building and official_building.status == "available":
        official_detail = " · ".join(
            value
            for value in (
                official_building.main_use,
                f"사용승인 {official_building.approval_date}" if official_building.approval_date else None,
            )
            if value
        )
        document_use = _comparable_text(building_ledger.property.main_use)
        official_use = _comparable_text(official_building.main_use)
        use_matches = (
            not document_use
            or not official_use
            or document_use in official_use
            or official_use in document_use
        )
        document_date = _comparable_text(building_ledger.property.approval_date)
        official_date = _comparable_text(official_building.approval_date)
        date_matches = not document_date or not official_date or document_date[:8] == official_date[:8]
        address_matches = _address_matches(address, official_building.address)
        document_illegal = building_ledger.property.is_illegal_building
        illegal_matches = (
            document_illegal == official_illegal
            if document_illegal is not None and official_illegal is not None
            else True
        )
        metadata_mismatch = not use_matches or not date_matches
        has_official_mismatch = (
            metadata_mismatch
            or address_matches is False
            or not illegal_matches
        )
        checks.append(
            CheckItem(
                label="입력 주소와 공식 주소",
                status=(
                    "verified" if address_matches is True
                    else "warning" if address_matches is False
                    else "needs_review"
                ),
                detail=(
                    "입력 주소가 건축HUB 공식 도로명주소와 일치합니다"
                    if address_matches is True
                    else "입력 주소가 건축HUB 공식 도로명주소와 다릅니다"
                    if address_matches is False
                    else "건축HUB 공식 도로명주소를 확인하지 못했습니다"
                ),
            )
        )
        checks.append(
            CheckItem(
                label="공식 건축물대장",
                status="warning" if metadata_mismatch else "verified",
                detail=(
                    "업로드 문서의 주용도 또는 사용승인일이 건축HUB와 다릅니다"
                    if metadata_mismatch
                    else official_detail or "건축HUB 표제부와 주소를 확인했습니다"
                ),
            )
        )

        illegal_check = next(
            (check for check in checks if check.label == "위반건축물 여부"),
            None,
        )
        if illegal_check and official_illegal is not None:
            illegal_check.status = "warning" if official_illegal else "verified"
            illegal_check.detail = (
                "건축HUB 공식 표제부에 위반건축물로 표시되어 있습니다"
                if official_illegal
                else "건축HUB 공식 표제부에서 위반건축물 표기가 확인되지 않았습니다"
            )
        elif illegal_check and illegal_check.status == "needs_review":
            illegal_check.detail = (
                "건축HUB 표제부 API가 위반 여부를 제공하지 않아 업로드 원문 확인이 필요합니다"
            )
    else:
        if official_building:
            checks.append(
                CheckItem(
                    label="공식 건축물대장",
                    status="needs_review",
                    detail=official_building.message or "건축HUB 대조 결과를 확인하지 못했습니다",
                )
            )

    if has_blocking_review or has_mismatch or has_official_mismatch:
        status = "needs_review"
    elif market and market.status == "available":
        status = "complete"
    else:
        status = "partial"

    if market:
        market_state = MarketDataState(
            status="available" if market.status == "available" else "unavailable",
            message=market.message,
            source="국토교통부 연립·다세대 매매 실거래가",
            method=market.method,
            as_of=market.as_of,
        )
    else:
        market_state = MarketDataState(
            status="not_connected",
            message="공공 실거래가 연동 전이라 예상 주택가액과 시세 비율을 계산하지 않았습니다.",
        )

    return AnalysisResponse(
        analysis_id=str(uuid4()),
        mode=mode,
        status=status,
        score=risk.score,
        grade=risk.grade,  # type: ignore[arg-type]
        headline=risk.headline,
        summary=risk.summary,
        facts=facts,
        signals=risk.signals,
        checks=checks,
        actions=risk.actions,
        market_data=market_state,
        ai_explanation=AIExplanation(
            status="disabled",
            provider="gemini",
            model="gemini-3.5-flash-lite",
            message="AI 설명 생성 전입니다.",
        ),
        documents=bundle,
        disclaimer=(
            "이 사전점검 결과는 입력 조건과 현재 서류를 바탕으로 한 참고 정보이며 "
            "계약서 교차검증, 법률 자문 또는 보증 가입 심사를 대신하지 않습니다."
            if mode == "precheck"
            else "이 결과는 계약 의사결정을 돕는 참고 정보이며 법률 자문이나 보증 가입 심사를 대신하지 않습니다."
        ),
    )
