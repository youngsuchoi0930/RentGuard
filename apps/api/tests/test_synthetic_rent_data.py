from app.services.rent_data_collector import parse_rent_payload
from app.services.synthetic_rent_data import make_synthetic_anomaly
from test_rent_data_collector import PAYLOAD


def _source_row():
    return parse_rent_payload(PAYLOAD, district_code="11500", district_name="강서구")[0][0]


def test_synthetic_deposit_spike_is_separate_and_recalculates_density():
    source = _source_row()
    synthetic = make_synthetic_anomaly(source, scenario="deposit_spike", seed=7)

    assert synthetic.source_kind == "synthetic"
    assert synthetic.label == "anomalous"
    assert synthetic.label_source == "synthetic"
    assert synthetic.synthetic_scenario == "deposit_spike"
    assert synthetic.features.deposit_million_won > source.features.deposit_million_won
    assert synthetic.features.deposit_per_m2_million_won == round(
        synthetic.features.deposit_million_won / synthetic.features.exclusive_area_m2,
        6,
    )


def test_synthetic_generation_is_deterministic_for_same_seed():
    first = make_synthetic_anomaly(_source_row(), scenario="renewal_jump", seed=11)
    second = make_synthetic_anomaly(_source_row(), scenario="renewal_jump", seed=11)

    assert first == second
