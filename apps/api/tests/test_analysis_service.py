from pathlib import Path

from app.services.analysis_service import build_analysis
from app.services.building_parser import extract_building_ledger
from app.services.public_data import MarketEstimate, OfficialBuilding, PublicDataResult
from app.services.registry_parser import extract_registry


def test_precheck_separates_official_address_from_document_ocr_review():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    ledger.property.is_illegal_building = None

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
    )

    official_address = next(check for check in analysis.checks if check.label == "입력 주소와 공식 주소")
    illegal = next(check for check in analysis.checks if check.label == "위반건축물 여부")
    assert official_address.status == "verified"
    assert illegal.status == "needs_review"
    assert "표제부 API가 위반 여부를 제공하지 않아" in illegal.detail
