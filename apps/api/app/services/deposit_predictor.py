from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings
from ..ml_schemas import PublicRentFeatureVector, PublicRentTrainingRow
from ..schemas import DepositMarketState
from .deposit_quantile_features import (
    deposit_model_vector,
    deposit_model_vector_v2,
    predicted_deposit_million_won,
)
from .market_anomaly_features import rent_mode
from .public_data import PublicDataResult


def _unavailable(message: str) -> DepositMarketState:
    return DepositMarketState(status="unavailable", message=message)


@lru_cache(maxsize=4)
def _load_artifact(path: str, modified_ns: int) -> dict[str, Any]:
    # joblib artifacts are executable pickle data. Only the configured trusted local
    # training output is loaded; uploaded/user-provided model files are never used.
    import joblib

    artifact = joblib.load(path)
    if artifact.get("schema_version") not in {
        "deposit-quantile-model-1.0",
        "deposit-quantile-model-2.0",
    }:
        raise ValueError("지원하지 않는 보증금 모델 형식입니다.")
    return artifact


@lru_cache(maxsize=4)
def _sha256(path: str, modified_ns: int) -> str:
    del modified_ns
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _load_manifest(path: str, modified_ns: int) -> dict[str, Any]:
    del modified_ns
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != "rentguard-model-manifest-1.0":
        raise ValueError("지원하지 않는 모델 manifest 형식입니다.")
    return payload


def _load_configured_artifact(
    config: Settings,
) -> tuple[Path, dict[str, Any], str]:
    model_path = Path(config.deposit_model_path).resolve()
    if not model_path.is_file():
        raise FileNotFoundError("학습된 보증금 모델 파일이 없습니다.")

    manifest_path = model_path.with_suffix(".manifest.json")
    integrity = "unverified"
    manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        manifest = _load_manifest(
            str(manifest_path),
            manifest_path.stat().st_mtime_ns,
        )
        if manifest.get("artifact") != model_path.name:
            raise ValueError("모델 manifest의 파일명이 일치하지 않습니다.")
        if manifest.get("size_bytes") != model_path.stat().st_size:
            raise ValueError("모델 파일 크기가 manifest와 일치하지 않습니다.")
        expected_hash = str(manifest.get("sha256", "")).lower()
        actual_hash = _sha256(str(model_path), model_path.stat().st_mtime_ns)
        if expected_hash != actual_hash:
            raise ValueError("모델 파일 해시가 manifest와 일치하지 않습니다.")
        integrity = "verified"
    elif config.require_deposit_model:
        raise FileNotFoundError("필수 모델 manifest 파일이 없습니다.")

    artifact = _load_artifact(str(model_path), model_path.stat().st_mtime_ns)
    if manifest and manifest.get("artifact_schema_version") != artifact.get(
        "schema_version"
    ):
        raise ValueError("모델 형식이 manifest와 일치하지 않습니다.")
    return model_path, artifact, integrity


def deposit_model_health(
    settings: Settings | None = None,
) -> dict[str, str | int | None]:
    config = settings or get_settings()
    try:
        model_path, artifact, integrity = _load_configured_artifact(config)
        periods = artifact.get("training_periods") or []
        return {
            "status": "ready",
            "artifact": model_path.name,
            "schema_version": str(artifact["schema_version"]),
            "training_period_end": str(max(periods)) if periods else None,
            "integrity": integrity,
            "size_bytes": model_path.stat().st_size,
        }
    except (
        ImportError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        AttributeError,
        EOFError,
        IndexError,
    ) as exc:
        return {
            "status": "unavailable",
            "artifact": Path(config.deposit_model_path).name,
            "schema_version": None,
            "training_period_end": None,
            "integrity": "failed",
            "size_bytes": None,
            "message": str(exc),
        }


def _model_row(
    *,
    public_data: PublicDataResult,
    deposit: int,
    monthly_rent: int,
    today: date,
    exclusive_area_m2: float | None = None,
    approval_date: str | None = None,
) -> PublicRentTrainingRow | None:
    address = public_data.address
    building = public_data.building
    # Uploaded ledger values are the stable snapshot for this analysis. Public
    # APIs enrich missing fields, but a transient Building HUB failure must not
    # change the model input for the same uploaded documents.
    area = exclusive_area_m2 or building.exclusive_area
    if address is None or area is None or area <= 0:
        return None
    approval_year = None
    effective_approval_date = approval_date or building.approval_date
    if effective_approval_date and effective_approval_date[:4].isdigit():
        approval_year = max(0, today.year - int(effective_approval_date[:4]))
    deposit_million = deposit / 1_000_000
    rent_million = monthly_rent / 1_000_000
    return PublicRentTrainingRow(
        sample_id="live-analysis",
        source_kind="public_transaction",
        features=PublicRentFeatureVector(
            district_code=address.sigungu_code,
            district_name=address.road_address.split()[1]
            if len(address.road_address.split()) > 1
            else address.sigungu_code,
            legal_dong_name=address.legal_dong_name,
            contract_year=today.year,
            contract_month=today.month,
            exclusive_area_m2=area,
            floor=None,
            building_age_years=approval_year,
            deposit_million_won=deposit_million,
            monthly_rent_million_won=rent_million,
            deposit_per_m2_million_won=deposit_million / area,
            monthly_rent_per_m2_million_won=rent_million / area,
            contract_type="unknown",
            renewal_right_used="unknown",
        ),
    )


def predict_deposit_market(
    *,
    public_data: PublicDataResult | None,
    deposit: int,
    monthly_rent: int,
    settings: Settings | None = None,
    today: date | None = None,
    exclusive_area_m2: float | None = None,
    approval_date: str | None = None,
) -> DepositMarketState:
    if public_data is None or public_data.address is None:
        return _unavailable("공공 주소정보를 확인하지 못해 유사 보증금 범위를 계산하지 않았습니다.")
    if not public_data.address.sigungu_code.startswith("11"):
        return DepositMarketState(
            status="out_of_scope",
            message="현재 보증금 모델은 서울 연립·다세대 신고자료만 지원합니다.",
        )
    if public_data.building.exclusive_area is None and exclusive_area_m2 is None:
        return _unavailable("건축물대장에서 전용면적을 확인하지 못해 보증금 모델을 적용하지 않았습니다.")

    config = settings or get_settings()
    if not Path(config.deposit_model_path).resolve().is_file():
        return _unavailable("학습된 보증금 모델 파일이 없어 시장 범위를 계산하지 않았습니다.")
    row = _model_row(
        public_data=public_data,
        deposit=deposit,
        monthly_rent=monthly_rent,
        today=today or date.today(),
        exclusive_area_m2=exclusive_area_m2,
        approval_date=approval_date,
    )
    if row is None:
        return _unavailable("보증금 예측에 필요한 주소 또는 전용면적이 부족합니다.")

    try:
        _, artifact, _ = _load_configured_artifact(config)
        mode = rent_mode(row)
        mode_models = artifact["models"][mode]
        if artifact["schema_version"] == "deposit-quantile-model-2.0":
            feature_versions = artifact.get("quantile_feature_versions", {})
            p50_builder = (
                deposit_model_vector
                if feature_versions.get("p50") == "v1"
                else deposit_model_vector_v2
            )
            p95_builder = (
                deposit_model_vector
                if feature_versions.get("p95") == "v1"
                else deposit_model_vector_v2
            )
            p50_vector = [p50_builder(row, artifact["peer_reference"])]
            p95_vector = [p95_builder(row, artifact["peer_reference"])]
            offsets = artifact.get("calibration_log_offsets", {}).get(mode, {})
        else:
            p50_vector = [deposit_model_vector(row, artifact["peer_reference"])]
            p95_vector = p50_vector
            offsets = {}
        p50_log = float(mode_models["p50"].predict(p50_vector)[0]) + float(
            offsets.get("p50", 0.0)
        )
        p95_log = max(
            p50_log,
            float(mode_models["p95"].predict(p95_vector)[0])
            + float(offsets.get("p95", 0.0)),
        )
        p50_won = int(round(predicted_deposit_million_won(row, p50_log) * 1_000_000 / 100_000) * 100_000)
        p95_won = int(round(predicted_deposit_million_won(row, p95_log) * 1_000_000 / 100_000) * 100_000)
        periods = artifact.get("training_periods") or []
        period_end = str(max(periods)) if periods else None
    except (
        ImportError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        AttributeError,
        OverflowError,
        EOFError,
        IndexError,
    ):
        return _unavailable("보증금 모델을 불러오거나 예측하지 못해 기존 규칙만 적용했습니다.")

    exceeds = deposit > p95_won
    return DepositMarketState(
        status="available",
        message=(
            "입력 보증금이 유사 계약의 예측 상위 경계를 넘었습니다. 원인을 추가 확인하세요."
            if exceeds
            else "입력 보증금이 유사 계약의 예측 시장 범위 안에 있습니다."
        ),
        expected_deposit=p50_won,
        upper_deposit=p95_won,
        upper_ratio=round(deposit / p95_won, 4) if p95_won > 0 else None,
        exceeds_upper=exceeds,
        model_version=str(artifact["schema_version"]),
        training_period_end=period_end,
    )
