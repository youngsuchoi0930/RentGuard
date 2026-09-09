from __future__ import annotations

import hashlib
import random
from typing import Literal

from ..ml_schemas import PublicRentTrainingRow


SyntheticScenario = Literal["deposit_spike", "rent_spike", "renewal_jump"]


def make_synthetic_anomaly(
    source: PublicRentTrainingRow,
    *,
    scenario: SyntheticScenario,
    seed: int,
) -> PublicRentTrainingRow:
    """Perturb a public row for pipeline testing, never for real-world evaluation."""
    rng = random.Random(f"{seed}:{source.sample_id}:{scenario}")
    row = source.model_copy(deep=True)
    features = row.features

    if scenario == "deposit_spike":
        features.deposit_million_won = round(
            max(features.deposit_million_won, 10) * rng.uniform(3.0, 6.0),
            6,
        )
    elif scenario == "rent_spike":
        base_rent = max(features.monthly_rent_million_won, features.exclusive_area_m2 * .015)
        features.monthly_rent_million_won = round(base_rent * rng.uniform(5.0, 10.0), 6)
    elif scenario == "renewal_jump":
        previous = max(features.deposit_million_won, 10)
        features.previous_deposit_million_won = round(previous, 6)
        features.deposit_million_won = round(previous * rng.uniform(2.0, 3.0), 6)
        features.deposit_change_ratio = round(
            (features.deposit_million_won - previous) / previous,
            6,
        )
        features.contract_type = "renewal"
    else:
        raise ValueError(f"지원하지 않는 합성 시나리오입니다: {scenario}")

    features.deposit_per_m2_million_won = round(
        features.deposit_million_won / features.exclusive_area_m2,
        6,
    )
    features.monthly_rent_per_m2_million_won = round(
        features.monthly_rent_million_won / features.exclusive_area_m2,
        6,
    )
    digest = hashlib.sha256(
        f"{seed}:{source.sample_id}:{scenario}".encode("utf-8"),
    ).hexdigest()[:20]
    row.sample_id = f"syn-{digest}"
    row.source_kind = "synthetic"
    row.label = "anomalous"
    row.label_source = "synthetic"
    row.synthetic_scenario = scenario
    return row
