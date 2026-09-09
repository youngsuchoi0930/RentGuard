from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.ml_schemas import MLDatasetRowRequest
from app.services.analysis_service import build_analysis
from app.services.building_parser import extract_building_ledger
from app.services.ml_dataset import build_ml_dataset_row
from app.services.public_data import MarketEstimate, OfficialBuilding, PublicDataResult
from app.services.registry_parser import extract_registry


def _analysis():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry = extract_registry((fixtures / "registry_risky_digital.pdf").read_bytes())
    ledger = extract_building_ledger((fixtures / "building_ledger_risky.pdf").read_bytes())
    return build_analysis(
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
                main_use="다세대주택",
                approval_date="2018-06-20",
                is_illegal_building=False,
            ),
            market=MarketEstimate(
                status="available",
                estimated_value=340_000_000,
                estimated_value_low=300_000_000,
                estimated_value_high=380_000_000,
                transaction_count=51,
                volatility=.238,
                message="테스트",
            ),
        ),
    )


def test_ml_row_contains_features_but_no_pii_or_rule_score():
    row = build_ml_dataset_row(MLDatasetRowRequest(
        analysis=_analysis(),
        case_group_id="CASE_0001",
        reference_year=2026,
    ))

    assert row.features.housing_category == "rowhouse_multifamily"
    assert row.features.deposit_million_won == 30
    assert row.features.monthly_rent_million_won == 1.3
    assert row.features.estimated_value_million_won == 340
    assert row.features.deposit_to_value_ratio == pytest.approx(30 / 340, abs=1e-6)
    assert row.features.total_burden_to_value_ratio == pytest.approx(140 / 340, abs=1e-6)
    assert row.features.annual_rent_to_value_ratio == pytest.approx(15.6 / 340, abs=1e-6)
    assert row.features.recent_transaction_count == 51
    assert row.quality.eligible_for_training is True

    serialized = row.model_dump_json()
    for forbidden in ("화곡로", "김민준", "raw_text", "analysis_id", '"score"', '"grade"'):
        assert forbidden not in serialized


def test_ml_row_excludes_missing_market_data_from_training():
    analysis = _analysis()
    analysis.facts.estimated_value = None
    analysis.facts.estimated_value_low = None
    analysis.facts.estimated_value_high = None
    analysis.facts.recent_transactions = 0

    row = build_ml_dataset_row(MLDatasetRowRequest(analysis=analysis))

    assert row.quality.eligible_for_training is False
    assert "estimated_value_missing" in row.quality.exclusion_reasons
    assert "market_sample_too_small" in row.quality.exclusion_reasons


def test_manual_label_requires_provenance():
    with pytest.raises(ValidationError):
        MLDatasetRowRequest(analysis=_analysis(), label="confirmed_risk")


def test_ml_preview_endpoint_returns_sanitized_row_without_saving():
    response = TestClient(app).post(
        "/api/v1/ml/dataset-rows/preview",
        json={
            "analysis": _analysis().model_dump(mode="json"),
            "source_kind": "real_anonymized",
            "label": "unlabeled",
            "label_source": "none",
            "case_group_id": "CASE_0002",
            "reference_year": 2026,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["features"]["monthly_rent_million_won"] == 1.3
    assert "analysis" not in payload
