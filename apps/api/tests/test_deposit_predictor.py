from datetime import date
from pathlib import Path

import joblib

from app.config import Settings
from app.services.deposit_predictor import (
    _model_row,
    deposit_model_health,
    predict_deposit_market,
)
from app.services.deposit_quantile_features import deposit_target
from app.services.market_anomaly_features import build_peer_reference
from app.services.public_data import (
    MarketEstimate,
    OfficialBuilding,
    PublicDataResult,
    ResolvedAddress,
)


class FixedPredictor:
    def __init__(self, prediction: float):
        self.prediction = prediction

    def predict(self, _matrix):
        return [self.prediction]


def _public_data(*, district_code: str = "11500", area: float | None = 50.0):
    return PublicDataResult(
        address=ResolvedAddress(
            road_address="서울특별시 강서구 곰달래로 35길 26",
            jibun_address="서울특별시 강서구 화곡동 1",
            zip_code="00000",
            building_name=None,
            adm_code=f"{district_code}10100",
            legal_dong_name="화곡동",
            mountain=False,
            lot_main=1,
            lot_sub=0,
        ),
        building=OfficialBuilding(
            status="available",
            exclusive_area=area,
            approval_date="20180101",
            main_use="다세대주택",
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
    )


def test_predictor_returns_expected_and_upper_deposit(tmp_path):
    public_data = _public_data()
    row = _model_row(
        public_data=public_data,
        deposit=30_000_000,
        monthly_rent=1_300_000,
        today=date(2026, 9, 10),
    )
    assert row is not None
    reference = build_peer_reference([row] * 100)
    center = deposit_target(row)
    model_path = tmp_path / "deposit.joblib"
    joblib.dump(
        {
            "schema_version": "deposit-quantile-model-1.0",
            "models": {
                "monthly": {
                    "p50": FixedPredictor(center),
                    "p95": FixedPredictor(center + .2),
                },
            },
            "peer_reference": reference,
            "training_periods": [202501, 202608],
        },
        model_path,
    )

    result = predict_deposit_market(
        public_data=public_data,
        deposit=30_000_000,
        monthly_rent=1_300_000,
        settings=Settings(DEPOSIT_MODEL_PATH=model_path),
        today=date(2026, 9, 10),
    )

    assert result.status == "available"
    assert result.expected_deposit == 30_000_000
    assert result.upper_deposit > result.expected_deposit
    assert result.exceeds_upper is False
    assert result.training_period_end == "202608"


def test_predictor_supports_v2_features_and_calibration(tmp_path):
    public_data = _public_data()
    row = _model_row(
        public_data=public_data,
        deposit=30_000_000,
        monthly_rent=1_300_000,
        today=date(2026, 9, 10),
    )
    assert row is not None
    reference = build_peer_reference([row] * 100)
    center = deposit_target(row)
    model_path = tmp_path / "deposit-v2.joblib"
    joblib.dump(
        {
            "schema_version": "deposit-quantile-model-2.0",
            "models": {
                "monthly": {
                    "p50": FixedPredictor(center),
                    "p95": FixedPredictor(center + .1),
                },
            },
            "peer_reference": reference,
            "calibration_log_offsets": {
                "monthly": {"p50": .05, "p95": .2},
            },
            "training_periods": [202409, 202603],
        },
        model_path,
    )

    result = predict_deposit_market(
        public_data=public_data,
        deposit=30_000_000,
        monthly_rent=1_300_000,
        settings=Settings(DEPOSIT_MODEL_PATH=model_path),
        today=date(2026, 9, 10),
    )

    assert result.status == "available"
    assert result.expected_deposit > 30_000_000
    assert result.upper_deposit > result.expected_deposit
    assert result.model_version == "deposit-quantile-model-2.0"
    assert result.training_period_end == "202603"


def test_predictor_rejects_non_seoul_scope(tmp_path):
    result = predict_deposit_market(
        public_data=_public_data(district_code="41135"),
        deposit=30_000_000,
        monthly_rent=0,
        settings=Settings(DEPOSIT_MODEL_PATH=tmp_path / "missing.joblib"),
    )

    assert result.status == "out_of_scope"
    assert "서울 연립·다세대" in result.message


def test_model_row_uses_uploaded_ledger_area_when_public_area_is_missing():
    row = _model_row(
        public_data=_public_data(area=None),
        deposit=30_000_000,
        monthly_rent=1_300_000,
        today=date(2026, 9, 10),
        exclusive_area_m2=84.59,
    )

    assert row is not None
    assert row.features.exclusive_area_m2 == 84.59


def test_model_row_prefers_uploaded_ledger_features_over_public_building():
    row = _model_row(
        public_data=_public_data(area=50.0),
        deposit=30_000_000,
        monthly_rent=1_300_000,
        today=date(2026, 9, 10),
        exclusive_area_m2=84.59,
        approval_date="1998-01-15",
    )

    assert row is not None
    assert row.features.exclusive_area_m2 == 84.59
    assert row.features.building_age_years == 28


def test_deposit_prediction_is_stable_when_building_hub_is_unavailable():
    root = Path(__file__).resolve().parents[3]
    model_path = root / "models" / "deposit-quantile-v2.joblib"
    settings = Settings(DEPOSIT_MODEL_PATH=model_path, REQUIRE_DEPOSIT_MODEL=True)
    available = _public_data(area=50.0)
    unavailable = PublicDataResult(
        address=available.address,
        building=OfficialBuilding(
            status="unavailable",
            message="건축HUB 응답을 확인하지 못했습니다.",
        ),
        market=available.market,
    )
    common = {
        "deposit": 30_000_000,
        "monthly_rent": 1_300_000,
        "settings": settings,
        "today": date(2026, 9, 10),
        "exclusive_area_m2": 84.59,
        "approval_date": "1998-01-15",
    }

    with_hub = predict_deposit_market(public_data=available, **common)
    without_hub = predict_deposit_market(public_data=unavailable, **common)

    assert with_hub.status == "available"
    assert without_hub.status == "available"
    assert with_hub.expected_deposit == without_hub.expected_deposit
    assert with_hub.upper_deposit == without_hub.upper_deposit


def test_deployed_v2_model_passes_manifest_verification():
    root = Path(__file__).resolve().parents[3]
    model_path = root / "models" / "deposit-quantile-v2.joblib"

    result = deposit_model_health(
        Settings(DEPOSIT_MODEL_PATH=model_path, REQUIRE_DEPOSIT_MODEL=True)
    )

    assert result["status"] == "ready"
    assert result["schema_version"] == "deposit-quantile-model-2.0"
    assert result["training_period_end"] == "202605"
    assert result["integrity"] == "verified"


def test_required_model_reports_unavailable_when_artifact_is_missing(tmp_path):
    result = deposit_model_health(
        Settings(
            DEPOSIT_MODEL_PATH=tmp_path / "missing.joblib",
            REQUIRE_DEPOSIT_MODEL=True,
        )
    )

    assert result["status"] == "unavailable"
    assert result["integrity"] == "failed"
