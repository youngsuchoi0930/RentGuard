from pathlib import Path

from app.services.analysis_service import build_analysis
from app.services.analysis_service import _building_use_matches
from app.services.building_parser import extract_building_ledger
from app.schemas import DepositMarketState, UserCorrection
from app.services.public_data import MarketEstimate, OfficialBuilding, PublicDataResult
from app.services.registry_parser import extract_registry


def test_communal_housing_parent_and_subtype_are_compatible():
    assert _building_use_matches("연립주택", "공동주택") is True
    assert _building_use_matches("다세대주택", "공동주택") is True
    assert _building_use_matches("업무시설", "공동주택") is False


def test_precheck_separates_official_address_from_document_ocr_review(monkeypatch):
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    ledger.property.is_illegal_building = False
    monkeypatch.setattr(
        "app.services.analysis_service.predict_deposit_market",
        lambda **_kwargs: DepositMarketState(
            status="available",
            message="입력 보증금이 유사 계약의 예측 상위 경계를 넘었습니다.",
            expected_deposit=20_000_000,
            upper_deposit=25_000_000,
            upper_ratio=1.2,
            exceeds_upper=True,
            model_version="deposit-quantile-model-1.0",
            training_period_end="202605",
        ),
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
    assert official_address.status == "verified"
    assert illegal.status == "needs_review"
    assert "사용자가 위반건축물 아님으로 입력했지만" in illegal.detail
    assert analysis.status == "needs_review"
    ml_signal = next(signal for signal in analysis.signals if signal.id == "deposit-market-upper")
    assert ml_signal.points == 0
    assert "25,000,000원" in ml_signal.evidence
    assert next(check for check in analysis.checks if check.label == "보증금 시장 범위").status == "warning"
