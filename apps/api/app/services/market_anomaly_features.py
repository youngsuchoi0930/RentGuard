from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from ..ml_schemas import PublicRentTrainingRow


NUMERIC_FEATURES = (
    "log_deposit_per_m2",
    "log_monthly_rent_per_m2",
    "log_exclusive_area",
    "floor",
    "building_age",
    "deposit_change_ratio",
    "monthly_rent_change_ratio",
    "contract_month_sin",
    "contract_month_cos",
    "peer_deposit_log_delta",
    "peer_deposit_robust_z",
    "peer_rent_log_delta",
    "peer_rent_robust_z",
    "log_peer_group_size",
)


@dataclass(frozen=True)
class PeerStat:
    count: int
    deposit_log_median: float
    deposit_log_mad: float
    rent_log_median: float
    rent_log_mad: float


@dataclass(frozen=True)
class PeerReference:
    exact: dict[str, PeerStat]
    district_area: dict[str, PeerStat]
    district: dict[str, PeerStat]
    global_mode: dict[str, PeerStat]


def rent_mode(row: PublicRentTrainingRow) -> str:
    return "monthly" if row.features.monthly_rent_million_won > 0 else "jeonse"


def area_band(area_m2: float) -> int:
    return max(0, int(round(area_m2 / 10) * 10))


def _keys(row: PublicRentTrainingRow) -> tuple[str, str, str, str]:
    features = row.features
    mode = rent_mode(row)
    band = area_band(features.exclusive_area_m2)
    return (
        f"{features.district_code}|{features.legal_dong_name}|{band}|{mode}",
        f"{features.district_code}|{band}|{mode}",
        f"{features.district_code}|{mode}",
        mode,
    )


def _stat(values: list[tuple[float, float]]) -> PeerStat:
    deposits = [value[0] for value in values]
    rents = [value[1] for value in values]
    deposit_median = statistics.median(deposits)
    rent_median = statistics.median(rents)
    return PeerStat(
        count=len(values),
        deposit_log_median=deposit_median,
        deposit_log_mad=statistics.median(abs(value - deposit_median) for value in deposits),
        rent_log_median=rent_median,
        rent_log_mad=statistics.median(abs(value - rent_median) for value in rents),
    )


def build_peer_reference(rows: Iterable[PublicRentTrainingRow]) -> PeerReference:
    exact: dict[str, list[tuple[float, float]]] = defaultdict(list)
    district_area: dict[str, list[tuple[float, float]]] = defaultdict(list)
    district: dict[str, list[tuple[float, float]]] = defaultdict(list)
    global_mode: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        values = (
            math.log1p(row.features.deposit_per_m2_million_won),
            math.log1p(row.features.monthly_rent_per_m2_million_won),
        )
        keys = _keys(row)
        exact[keys[0]].append(values)
        district_area[keys[1]].append(values)
        district[keys[2]].append(values)
        global_mode[keys[3]].append(values)
    return PeerReference(
        exact={key: _stat(values) for key, values in exact.items() if len(values) >= 20},
        district_area={
            key: _stat(values)
            for key, values in district_area.items()
            if len(values) >= 40
        },
        district={key: _stat(values) for key, values in district.items() if len(values) >= 80},
        global_mode={key: _stat(values) for key, values in global_mode.items()},
    )


def peer_stat(row: PublicRentTrainingRow, reference: PeerReference) -> PeerStat:
    keys = _keys(row)
    for table, key in (
        (reference.exact, keys[0]),
        (reference.district_area, keys[1]),
        (reference.district, keys[2]),
        (reference.global_mode, keys[3]),
    ):
        if key in table:
            return table[key]
    raise ValueError("비교 가능한 전월세 기준 그룹이 없습니다.")


def _robust_z(value: float, median: float, mad: float) -> float:
    # 1.4826 scales MAD toward standard deviation; the floor avoids zero spread.
    return (value - median) / max(mad * 1.4826, .05)


def model_vector(row: PublicRentTrainingRow, reference: PeerReference) -> list[float]:
    features = row.features
    deposit_log = math.log1p(features.deposit_per_m2_million_won)
    rent_log = math.log1p(features.monthly_rent_per_m2_million_won)
    comparison = peer_stat(row, reference)
    angle = 2 * math.pi * (features.contract_month - 1) / 12
    return [
        deposit_log,
        rent_log,
        math.log1p(features.exclusive_area_m2),
        float(features.floor) if features.floor is not None else math.nan,
        float(features.building_age_years) if features.building_age_years is not None else math.nan,
        features.deposit_change_ratio if features.deposit_change_ratio is not None else math.nan,
        features.monthly_rent_change_ratio if features.monthly_rent_change_ratio is not None else math.nan,
        math.sin(angle),
        math.cos(angle),
        deposit_log - comparison.deposit_log_median,
        _robust_z(deposit_log, comparison.deposit_log_median, comparison.deposit_log_mad),
        rent_log - comparison.rent_log_median,
        _robust_z(rent_log, comparison.rent_log_median, comparison.rent_log_mad),
        math.log1p(comparison.count),
    ]
