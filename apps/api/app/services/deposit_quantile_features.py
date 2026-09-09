from __future__ import annotations

import math

from ..ml_schemas import PublicRentTrainingRow
from .market_anomaly_features import PeerReference, peer_stat


DEPOSIT_MODEL_FEATURES = (
    "log_exclusive_area",
    "floor",
    "building_age",
    "log_monthly_rent_per_m2",
    "contract_month_sin",
    "contract_month_cos",
    "contract_year_offset",
    "is_renewal",
    "log_previous_deposit_per_m2",
    "peer_deposit_log_median",
    "peer_deposit_log_mad",
    "log_peer_group_size",
)


def deposit_target(row: PublicRentTrainingRow) -> float:
    """Return log deposit density, the regression target."""
    return math.log1p(row.features.deposit_per_m2_million_won)


def deposit_model_vector(
    row: PublicRentTrainingRow,
    reference: PeerReference,
) -> list[float]:
    """Build predictors without using the current deposit amount.

    The peer statistics must be built only from the training partition. The current
    deposit is deliberately absent so the model can score a new proposed contract.
    """
    features = row.features
    comparison = peer_stat(row, reference)
    angle = 2 * math.pi * (features.contract_month - 1) / 12
    previous_density = (
        features.previous_deposit_million_won / features.exclusive_area_m2
        if features.previous_deposit_million_won is not None
        else math.nan
    )
    return [
        math.log1p(features.exclusive_area_m2),
        float(features.floor) if features.floor is not None else math.nan,
        float(features.building_age_years)
        if features.building_age_years is not None
        else math.nan,
        math.log1p(features.monthly_rent_per_m2_million_won),
        math.sin(angle),
        math.cos(angle),
        float(features.contract_year - 2020),
        1.0 if features.contract_type == "renewal" else 0.0,
        math.log1p(previous_density) if not math.isnan(previous_density) else math.nan,
        comparison.deposit_log_median,
        comparison.deposit_log_mad,
        math.log1p(comparison.count),
    ]


def predicted_deposit_million_won(
    row: PublicRentTrainingRow,
    predicted_log_density: float,
) -> float:
    density = max(0.0, math.expm1(predicted_log_density))
    return density * row.features.exclusive_area_m2
