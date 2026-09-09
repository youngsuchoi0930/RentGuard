from app.services.market_anomaly_features import (
    NUMERIC_FEATURES,
    build_peer_reference,
    model_vector,
    peer_stat,
)
from app.services.rent_data_collector import parse_rent_payload
from app.services.synthetic_rent_data import make_synthetic_anomaly
from test_rent_data_collector import PAYLOAD


def _source_row():
    return parse_rent_payload(PAYLOAD, district_code="11500", district_name="강서구")[0][0]


def test_peer_features_make_deposit_spike_visible_against_same_group():
    source = _source_row()
    reference = build_peer_reference([source] * 100)
    synthetic = make_synthetic_anomaly(source, scenario="deposit_spike", seed=17)

    source_vector = model_vector(source, reference)
    synthetic_vector = model_vector(synthetic, reference)
    deposit_z_index = NUMERIC_FEATURES.index("peer_deposit_robust_z")

    assert peer_stat(source, reference).count == 100
    assert source_vector[deposit_z_index] == 0
    assert synthetic_vector[deposit_z_index] > 10


def test_peer_reference_falls_back_when_exact_group_is_unseen():
    source = _source_row()
    reference = build_peer_reference([source] * 100)
    unseen = source.model_copy(deep=True)
    unseen.features.legal_dong_name = "새로운동"

    assert peer_stat(unseen, reference).count == 100
