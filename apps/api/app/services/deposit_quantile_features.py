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


DEPOSIT_MODEL_FEATURES_V2 = (
    "log_exclusive_area",
    "floor",
    "is_basement",
    "log_absolute_floor",
    "building_age",
    "log_building_age",
    "log_monthly_rent_per_m2",
    "peer_rent_log_delta",
    "peer_rent_robust_z",
    "contract_month_sin",
    "contract_month_cos",
    "contract_year_offset",
    "is_new_contract",
    "is_renewal",
    "is_contract_type_unknown",
    "renewal_right_used",
    "log_previous_deposit_per_m2",
    "log_previous_monthly_rent_per_m2",
    "peer_deposit_log_median",
    "peer_deposit_log_mad",
    "peer_rent_log_median",
    "peer_rent_log_mad",
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


def _robust_z(value: float, median: float, mad: float) -> float:
    return (value - median) / max(mad * 1.4826, .05)


def deposit_model_vector_v2(
    row: PublicRentTrainingRow,
    reference: PeerReference,
) -> list[float]:
    """Build the v2 predictors without using the proposed deposit amount."""
    features = row.features
    comparison = peer_stat(row, reference)
    angle = 2 * math.pi * (features.contract_month - 1) / 12
    floor = float(features.floor) if features.floor is not None else math.nan
    age = (
        float(features.building_age_years)
        if features.building_age_years is not None
        else math.nan
    )
    previous_deposit_density = (
        features.previous_deposit_million_won / features.exclusive_area_m2
        if features.previous_deposit_million_won is not None
        else math.nan
    )
    previous_rent_density = (
        features.previous_monthly_rent_million_won / features.exclusive_area_m2
        if features.previous_monthly_rent_million_won is not None
        else math.nan
    )
    rent_log = math.log1p(features.monthly_rent_per_m2_million_won)
    return [
        math.log1p(features.exclusive_area_m2),
        floor,
        1.0 if features.floor is not None and features.floor < 0 else 0.0,
        math.log1p(abs(floor)) if not math.isnan(floor) else math.nan,
        age,
        math.log1p(age) if not math.isnan(age) else math.nan,
        rent_log,
        rent_log - comparison.rent_log_median,
        _robust_z(rent_log, comparison.rent_log_median, comparison.rent_log_mad),
        math.sin(angle),
        math.cos(angle),
        float(features.contract_year - 2020),
        1.0 if features.contract_type == "new" else 0.0,
        1.0 if features.contract_type == "renewal" else 0.0,
        1.0 if features.contract_type == "unknown" else 0.0,
        1.0 if features.renewal_right_used == "yes" else 0.0,
        math.log1p(previous_deposit_density)
        if not math.isnan(previous_deposit_density)
        else math.nan,
        math.log1p(previous_rent_density)
        if not math.isnan(previous_rent_density)
        else math.nan,
        comparison.deposit_log_median,
        comparison.deposit_log_mad,
        comparison.rent_log_median,
        comparison.rent_log_mad,
        math.log1p(comparison.count),
    ]


def predicted_deposit_million_won(
    row: PublicRentTrainingRow,
    predicted_log_density: float,
) -> float:
    density = max(0.0, math.expm1(predicted_log_density))
    return density * row.features.exclusive_area_m2
