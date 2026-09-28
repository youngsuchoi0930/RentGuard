from pathlib import Path

from app.services.analysis_service import _registry_right_findings, build_analysis
from app.services.analysis_service import _building_use_matches
from app.services.building_parser import extract_building_ledger
from app.schemas import DepositMarketState, UserCorrection
from app.services.public_data import MarketEstimate, OfficialBuilding, PublicDataResult
from app.services.registry_parser import extract_registry
from app.registry_schemas import EncumbranceEntry, RegistryExtraction, RegistryMetadata, RegistryProperty


def test_communal_housing_parent_and_subtype_are_compatible():
    assert _building_use_matches("연립주택", "공동주택") is True
    assert _building_use_matches("다세대주택", "공동주택") is True
    assert _building_use_matches("업무시설", "공동주택") is False


def test_registry_right_findings_ignore_cancelled_rights_and_score_active_ones():
    registry = RegistryExtraction(
        document=RegistryMetadata(
            certificate_type="full_with_cancelled",
            property_type="condominium",
            pages=2,
        ),
        property=RegistryProperty(road_address="서울특별시 강서구 안심로 1"),
        ownership=[],
        encumbrances=[
            EncumbranceEntry(
                rank="2",
                right_type="provisional_seizure",
                status="cancelled",
                registered_at="2021-02-03",
            ),
            EncumbranceEntry(
                rank="3",
                right_type="seizure",
                status="active",
                registered_at="2022-03-04",
            ),
            EncumbranceEntry(
                rank="4",
                right_type="trust",
                status="active",
                registered_at="2023-04-05",
            ),
        ],
        extraction_method="pdf_text",
        confidence=1.0,
    )

    signals, actions, check = _registry_right_findings(registry, {})

    assert {signal.id for signal in signals} == {
        "registry-right-seizure",
        "registry-right-trust",
    }
    assert sum(signal.points for signal in signals) == 55
    assert len(actions) == 2
    assert check.status == "warning"
    assert "말소 1건은 위험 계산에서 제외" in check.detail


def test_build_analysis_adds_active_registry_rights_to_risk_result():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    registry.encumbrances.extend([
        EncumbranceEntry(
            rank="4",
            right_type="seizure",
            status="active",
            registered_at="2025-01-02",
        ),
        EncumbranceEntry(
            rank="5",
            right_type="trust",
            status="cancelled",
            registered_at="2025-02-03",
        ),
    ])

    analysis = build_analysis(
        mode="precheck",
        address="서울특별시 강서구 화곡로 123",
        deposit=30_000_000,
        monthly_rent=1_000_000,
        registry=registry,
        building_ledger=ledger,
        lease_contract=None,
    )

    assert any(signal.id == "registry-right-seizure" for signal in analysis.signals)
    assert not any(signal.id == "registry-right-trust" for signal in analysis.signals)
    assert analysis.score >= 25
    assert analysis.grade == "주의"
    rights_check = next(check for check in analysis.checks if check.label == "등기 권리관계")
    assert rights_check.status == "warning"
    assert "말소 1건은 위험 계산에서 제외" in rights_check.detail


def test_precheck_separates_official_address_from_document_ocr_review(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    ledger.property.is_illegal_building = False
    ledger.property.exclusive_area = 84.59
    prediction_inputs = {}

    def fake_predict_deposit_market(**kwargs):
        prediction_inputs.update(kwargs)
        return DepositMarketState(
            status="available",
            message="입력 보증금이 유사 계약의 예측 상위 경계를 넘었습니다.",
            expected_deposit=20_000_000,
            upper_deposit=25_000_000,
            upper_ratio=1.2,
            exceeds_upper=True,
            model_version="deposit-quantile-model-1.0",
            training_period_end="202605",
        )

    monkeypatch.setattr(
        "app.services.analysis_service.predict_deposit_market",
        fake_predict_deposit_market,
    )

    analysis = build_analysis(
        mode="precheck",
        address="서울특별시 강서구 화곡로 123, 301호",
        deposit=30_000_000,
        monthly_rent=1_300_000,
        registry=registry,
        building_ledger=ledger,
        lease_contract=None,
        public_data=PublicDataResult(
            address=None,
            building=OfficialBuilding(
                status="available",
                address="서울특별시 강서구 화곡로 123 (화곡동)",
                main_use="다세대주택",
                approval_date="2017-06-20",
                exclusive_area=ledger.property.exclusive_area,
                is_illegal_building=None,
            ),
            market=MarketEstimate(
                status="unavailable",
                estimated_value=None,
                estimated_value_low=None,
                estimated_value_high=None,
                transaction_count=0,
                volatility=None,
                message="테스트",
            ),
        ),
        corrections=[
            UserCorrection(
                field="building_ledger.property.is_illegal_building",
                label="위반건축물 여부",
                previous_value=None,
                corrected_value=False,
            )
        ],
    )

    official_address = next(check for check in analysis.checks if check.label == "입력 주소와 공식 주소")
    illegal = next(check for check in analysis.checks if check.label == "위반건축물 여부")
    official_ledger = next(check for check in analysis.checks if check.label == "공식 건축물대장")
    assert official_address.status == "verified"
    comparisons = {item.label: item for item in official_ledger.comparisons}
    assert comparisons["주용도"].status == "verified"
    assert comparisons["전유면적"].status == "verified"
    assert illegal.status == "needs_review"
    assert "사용자가 위반건축물 아님으로 입력했지만" in illegal.detail
    assert illegal.comparisons[0].official_value is None
    assert "정부24·세움터" in illegal.next_step
    assert analysis.status == "needs_review"
    ml_signal = next(signal for signal in analysis.signals if signal.id == "deposit-market-upper")
    assert ml_signal.points == 0
    assert "25,000,000원" in ml_signal.evidence
    assert next(check for check in analysis.checks if check.label == "보증금 시장 범위").status == "warning"
    assert prediction_inputs["exclusive_area_m2"] == ledger.property.exclusive_area
    assert prediction_inputs["approval_date"] == ledger.property.approval_date


def test_official_building_area_mismatch_is_visible_and_requires_review():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    ledger.property.exclusive_area = 84.59

    analysis = build_analysis(
        mode="precheck",
        address="서울특별시 강서구 화곡로 123, 301호",
        deposit=30_000_000,
        monthly_rent=1_300_000,
        registry=registry,
        building_ledger=ledger,
        lease_contract=None,
        public_data=PublicDataResult(
            address=None,
            building=OfficialBuilding(
                status="available",
                address="서울특별시 강서구 화곡로 123 (화곡동)",
                main_use=ledger.property.main_use,
                approval_date=ledger.property.approval_date,
                exclusive_area=(ledger.property.exclusive_area or 0) + 1,
                is_illegal_building=None,
            ),
            market=MarketEstimate(
                status="unavailable",
                estimated_value=None,
                estimated_value_low=None,
                estimated_value_high=None,
                transaction_count=0,
                volatility=None,
                message="테스트",
            ),
        ),
    )

    official_ledger = next(check for check in analysis.checks if check.label == "공식 건축물대장")
    area = next(item for item in official_ledger.comparisons if item.label == "전유면적")
    assert official_ledger.status == "warning"
    assert area.status == "warning"
    assert "전유면적" in official_ledger.detail
    assert official_ledger.next_step is not None
    assert analysis.status == "needs_review"


def test_building_hub_outage_does_not_change_document_or_market_calculations():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    ledger.property.is_illegal_building = False
    shared_market = MarketEstimate(
        status="available",
        estimated_value=220_000_000,
        estimated_value_low=200_000_000,
        estimated_value_high=240_000_000,
        transaction_count=8,
        volatility=.05,
        message="동일한 실거래가 스냅샷",
        method="테스트 중간가격",
        as_of="202608",
    )

    available = build_analysis(
        mode="precheck",
        address="서울특별시 강서구 화곡로 123",
        deposit=30_000_000,
        monthly_rent=1_300_000,
        registry=registry,
        building_ledger=ledger,
        lease_contract=None,
        public_data=PublicDataResult(
            address=None,
            building=OfficialBuilding(
                status="available",
                address="서울특별시 강서구 화곡로 123",
                main_use=ledger.property.main_use,
                approval_date=ledger.property.approval_date,
                exclusive_area=ledger.property.exclusive_area,
                is_illegal_building=False,
                message="건축HUB 공식 표제부를 확인했습니다.",
            ),
            market=shared_market,
        ),
    )
    unavailable = build_analysis(
        mode="precheck",
        address="서울특별시 강서구 화곡로 123",
        deposit=30_000_000,
        monthly_rent=1_300_000,
        registry=registry,
        building_ledger=ledger,
        lease_contract=None,
        public_data=PublicDataResult(
            address=None,
            building=OfficialBuilding(
                status="unavailable",
                message="건축HUB 표제부 응답 시간이 초과되었습니다.",
            ),
            market=shared_market,
        ),
    )

    invariant_fields = (
        "owner",
        "mortgage_amount",
        "deposit",
        "monthly_rent",
        "estimated_value",
        "estimated_value_low",
        "estimated_value_high",
    )
    assert {
        field: getattr(available.facts, field) for field in invariant_fields
    } == {
        field: getattr(unavailable.facts, field) for field in invariant_fields
    }
    assert available.score == unavailable.score
    assert {signal.id for signal in available.signals} == {
        signal.id for signal in unavailable.signals
    }
    assert available.market_data == unavailable.market_data
    outage_check = next(
        check for check in unavailable.checks if check.label == "공식 건축물대장"
    )
    assert outage_check.status == "needs_review"
    assert "응답 시간이 초과" in outage_check.detail
