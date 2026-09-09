from __future__ import annotations

from typing import Literal
from uuid import uuid4

from ..building_schemas import BuildingLedgerExtraction
from ..lease_schemas import LeaseContractExtraction
from ..registry_schemas import RegistryExtraction, ReviewItem, SourceEvidence
from ..risk_engine import analyze_risk
from ..schemas import (
    AIExplanation,
    AnalysisResponse,
    CheckItem,
    EvidenceReference,
    ExtractedFacts,
    MarketDataState,
    UserCorrection,
)
from .cross_checker import _address_matches, cross_check_documents
from .public_data import PublicDataResult


def _approval_year(ledger: BuildingLedgerExtraction) -> int | None:
    value = ledger.property.approval_date
    if not value or len(value) < 4 or not value[:4].isdigit():
        return None
    return int(value[:4])


def _reference(
    *,
    document: Literal["registry", "building_ledger", "lease_contract"],
    field: str,
    label: str,
    evidence: SourceEvidence | None,
    corrections: dict[str, UserCorrection],
) -> EvidenceReference | None:
    correction = corrections.get(field)
    if evidence is None and correction is None:
        return None
    return EvidenceReference(
        document=document,
        field=field,
        label=label,
        page=evidence.page if evidence else None,
        section=evidence.section if evidence else None,
        raw_text=evidence.raw_text if evidence else None,
        extraction_method=evidence.extraction_method if evidence else None,
        confidence=evidence.confidence if evidence else None,
        corrected=correction is not None,
        previous_value=correction.previous_value if correction else None,
        corrected_value=correction.corrected_value if correction else None,
    )


def _source_map(
    registry: RegistryExtraction,
    building_ledger: BuildingLedgerExtraction,
    lease_contract: LeaseContractExtraction | None,
    corrections: list[UserCorrection],
) -> dict[str, list[EvidenceReference]]:
    correction_map = {item.field: item for item in corrections}

    def refs(*items: EvidenceReference | None) -> list[EvidenceReference]:
        return [item for item in items if item is not None]

    registry_addresses = refs(*(
        _reference(
            document="registry",
            field=f"registry.property.{field}",
            label=f"등기부 {label}",
            evidence=registry.evidence.get(field),
            corrections=correction_map,
        )
        for field, label in (("road_address", "도로명주소"), ("lot_address", "지번주소"))
    ))
    building_addresses = refs(*(
        _reference(
            document="building_ledger",
            field=f"building_ledger.property.{field}",
            label=f"건축물대장 {label}",
            evidence=building_ledger.evidence.get(field),
            corrections=correction_map,
        )
        for field, label in (("road_address", "도로명주소"), ("lot_address", "지번주소"))
    ))
    owners = refs(*(
        _reference(
            document="registry",
            field=f"registry.ownership.{index}.owner_name",
            label="등기 소유자",
            evidence=entry.evidence,
            corrections=correction_map,
        )
        for index, entry in enumerate(registry.ownership)
    ))
    mortgages = refs(*(
        _reference(
            document="registry",
            field=f"registry.encumbrances.{index}.maximum_claim_amount",
            label="근저당 채권최고액",
            evidence=entry.evidence,
            corrections=correction_map,
        )
        for index, entry in enumerate(registry.encumbrances)
        if entry.right_type == "mortgage" and entry.status == "active"
    ))
    illegal = refs(_reference(
        document="building_ledger",
        field="building_ledger.property.is_illegal_building",
        label="위반건축물 여부",
        evidence=building_ledger.evidence.get("is_illegal_building"),
        corrections=correction_map,
    ))
    lease_addresses: list[EvidenceReference] = []
    landlords: list[EvidenceReference] = []
    deposits: list[EvidenceReference] = []
    rents: list[EvidenceReference] = []
    if lease_contract:
        lease_addresses = refs(_reference(
            document="lease_contract",
            field="lease_contract.property.address",
            label="계약서 목적물 주소",
            evidence=lease_contract.evidence.get("address"),
            corrections=correction_map,
        ))
        landlords = refs(*(
            _reference(
                document="lease_contract",
                field=f"lease_contract.parties.{index}.name",
                label="계약서 임대인",
                evidence=party.evidence,
                corrections=correction_map,
            )
            for index, party in enumerate(lease_contract.parties)
            if party.role == "landlord"
        ))
        deposits = refs(_reference(
            document="lease_contract",
            field="lease_contract.deposit.value",
            label="계약서 보증금",
            evidence=lease_contract.deposit.evidence,
            corrections=correction_map,
        ))
        rents = refs(_reference(
            document="lease_contract",
            field="lease_contract.monthly_rent.value",
            label="계약서 월세",
            evidence=lease_contract.monthly_rent.evidence,
            corrections=correction_map,
        ))

    addresses = registry_addresses + building_addresses + lease_addresses
    return {
        "registry-owner": owners,
        "owner-landlord": owners + landlords,
        "property-address": addresses,
        "deposit": deposits,
        "monthly-rent": rents,
        "illegal-building": illegal,
        "senior-burden": mortgages + deposits,
        "mortgage": mortgages,
        "mortgage-present": mortgages,
        "deposit-ratio": deposits,
        "owner-mismatch": owners + landlords,
    }


def _active_reviews(
    registry: RegistryExtraction,
    building_ledger: BuildingLedgerExtraction,
    lease_contract: LeaseContractExtraction | None,
) -> list[ReviewItem]:
    resolved_registry = {
        "OWNER_NOT_FOUND": any(entry.owner_name.strip() for entry in registry.ownership),
        "ADDRESS_NOT_FOUND": bool(registry.property.road_address or registry.property.lot_address),
        "MORTGAGE_AMOUNT_NOT_FOUND": all(
            entry.maximum_claim_amount is not None
            for entry in registry.encumbrances
            if entry.right_type == "mortgage"
        ),
    }
    resolved_building = {
        "LEDGER_ADDRESS_NOT_FOUND": bool(
            building_ledger.property.road_address or building_ledger.property.lot_address
        ),
        "BUILDING_USE_NOT_FOUND": bool(building_ledger.property.main_use),
        "ILLEGAL_STATUS_UNKNOWN": building_ledger.property.is_illegal_building is not None,
    }
    reviews = [
        item for item in registry.needs_review
        if not resolved_registry.get(item.code, False)
    ] + [
        item for item in building_ledger.needs_review
        if not resolved_building.get(item.code, False)
    ]
    if lease_contract:
        landlord_found = any(
            party.role == "landlord" and party.name.strip()
            for party in lease_contract.parties
        )
        resolved_lease = {
            "CONTRACT_ADDRESS_NOT_FOUND": bool(lease_contract.property.address),
            "LANDLORD_NOT_FOUND": landlord_found,
            "DEPOSIT_NOT_FOUND": lease_contract.deposit.value is not None,
            "LEASE_PERIOD_NOT_FOUND": bool(
                lease_contract.lease_period.start and lease_contract.lease_period.end
            ),
        }
        reviews.extend(
            item for item in lease_contract.needs_review
            if not resolved_lease.get(item.code, False)
        )
    return reviews


def _bundle_checks(bundle, sources: dict[str, list[EvidenceReference]]) -> list[CheckItem]:
    status_map = {
        "verified": "verified",
        "mismatch": "warning",
        "needs_review": "needs_review",
    }
    checks = [
        CheckItem(
            label=item.label,
            status=status_map[item.status],
            detail=item.detail,
            sources=sources.get(item.id, []),
        )
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
    corrections: list[UserCorrection] | None = None,
) -> AnalysisResponse:
    applied_corrections = corrections or []
    bundle = cross_check_documents(
        registry,
        building_ledger,
        lease_contract,
        input_address=address,
        input_deposit=deposit,
        input_monthly_rent=monthly_rent,
    )
    sources = _source_map(registry, building_ledger, lease_contract, applied_corrections)
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
    for signal in risk.signals:
        signal.sources = sources.get(signal.id, [])
    document_reviews = _active_reviews(registry, building_ledger, lease_contract)
    has_blocking_review = any(item.severity == "blocking" for item in document_reviews)
    has_mismatch = any(item.status == "mismatch" for item in bundle.cross_checks)
    has_official_mismatch = False
    checks = _bundle_checks(bundle, sources)
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
        corrections=applied_corrections,
        disclaimer=(
            "이 사전점검 결과는 입력 조건과 현재 서류를 바탕으로 한 참고 정보이며 "
            "계약서 교차검증, 법률 자문 또는 보증 가입 심사를 대신하지 않습니다."
            if mode == "precheck"
            else "이 결과는 계약 의사결정을 돕는 참고 정보이며 법률 자문이나 보증 가입 심사를 대신하지 않습니다."
        ),
    )
