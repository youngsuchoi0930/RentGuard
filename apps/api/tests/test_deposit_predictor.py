from datetime import date

import joblib

from app.config import Settings
from app.services.deposit_predictor import _model_row, predict_deposit_market
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
