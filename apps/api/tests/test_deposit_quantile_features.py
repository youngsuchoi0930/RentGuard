import math

from app.services.deposit_quantile_features import (
    DEPOSIT_MODEL_FEATURES,
    DEPOSIT_MODEL_FEATURES_V2,
    deposit_model_vector,
    deposit_model_vector_v2,
    deposit_target,
    predicted_deposit_million_won,
)
from app.services.market_anomaly_features import build_peer_reference
from app.services.rent_data_collector import parse_rent_payload
from app.services.synthetic_rent_data import make_synthetic_anomaly
from test_rent_data_collector import PAYLOAD


def _source_row():
    return parse_rent_payload(PAYLOAD, district_code="11500", district_name="강서구")[0][0]


def test_deposit_predictors_do_not_contain_current_deposit():
    source = _source_row()
    reference = build_peer_reference([source] * 100)
    synthetic = make_synthetic_anomaly(source, scenario="deposit_spike", seed=17)

    assert deposit_model_vector(source, reference) == deposit_model_vector(
        synthetic,
        reference,
    )
    assert deposit_target(synthetic) > deposit_target(source)
    assert "deposit_million_won" not in DEPOSIT_MODEL_FEATURES


def test_v2_predictors_do_not_contain_current_deposit():
    source = _source_row()
    reference = build_peer_reference([source] * 100)
    synthetic = make_synthetic_anomaly(source, scenario="deposit_spike", seed=17)

    assert deposit_model_vector_v2(source, reference) == deposit_model_vector_v2(
        synthetic,
        reference,
    )
    assert len(deposit_model_vector_v2(source, reference)) == len(
        DEPOSIT_MODEL_FEATURES_V2
    )
    assert "deposit_million_won" not in DEPOSIT_MODEL_FEATURES_V2


def test_log_density_prediction_converts_back_to_total_deposit():
    source = _source_row()

    predicted = predicted_deposit_million_won(source, deposit_target(source))

    assert math.isclose(predicted, source.features.deposit_million_won, rel_tol=1e-6)
