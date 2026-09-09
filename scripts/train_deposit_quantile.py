from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import sklearn  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402

from app.ml_schemas import PublicRentTrainingRow  # noqa: E402
from app.services.deposit_quantile_features import (  # noqa: E402
    DEPOSIT_MODEL_FEATURES,
    deposit_model_vector,
    deposit_target,
    predicted_deposit_million_won,
)
from app.services.market_anomaly_features import (  # noqa: E402
    PeerReference,
    build_peer_reference,
    rent_mode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="보증금 전용 분위수 회귀 모델을 학습합니다.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "ml" / "seoul-rh-rent-market-v1.jsonl",
    )
    parser.add_argument(
        "--synthetic",
        type=Path,
        default=ROOT / "data" / "ml" / "seoul-rh-rent-synthetic-v1.jsonl",
    )
    parser.add_argument(
        "--model-output",
        type=Path,
        default=ROOT / "models" / "deposit-quantile-v1.joblib",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=ROOT / "data" / "ml" / "deposit-quantile-v1-report.json",
    )
    parser.add_argument("--max-train", type=int, default=120_000)
    parser.add_argument("--max-holdout", type=int, default=50_000)
    parser.add_argument("--holdout-months", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _period(row: PublicRentTrainingRow) -> int:
    return row.features.contract_year * 100 + row.features.contract_month


def _eligible(row: PublicRentTrainingRow) -> bool:
    features = row.features
    return (
        features.deposit_million_won > 0
        and features.deposit_per_m2_million_won > 0
        and 5 <= features.exclusive_area_m2 <= 300
    )


def _reservoir_add(
    reservoir: list[PublicRentTrainingRow],
    row: PublicRentTrainingRow,
    *,
    seen: int,
    limit: int,
    rng: random.Random,
) -> None:
    if len(reservoir) < limit:
        reservoir.append(row)
        return
    replacement = rng.randint(0, seen - 1)
    if replacement < limit:
        reservoir[replacement] = row


def _load_periods(path: Path) -> list[int]:
    periods: set[int] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = PublicRentTrainingRow.model_validate_json(line)
            if _eligible(row):
                periods.add(_period(row))
    return sorted(periods)


def _load_split(
    path: Path,
    *,
    holdout_periods: set[int],
    train_limit: int,
    holdout_limit: int,
    seed: int,
) -> tuple[list[PublicRentTrainingRow], list[PublicRentTrainingRow], int, int, int]:
    train: list[PublicRentTrainingRow] = []
    holdout: list[PublicRentTrainingRow] = []
    train_seen = holdout_seen = excluded = 0
    train_rng = random.Random(seed)
    holdout_rng = random.Random(seed + 1)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = PublicRentTrainingRow.model_validate_json(line)
            if not _eligible(row):
                excluded += 1
                continue
            if _period(row) in holdout_periods:
                holdout_seen += 1
                _reservoir_add(
                    holdout,
                    row,
                    seen=holdout_seen,
                    limit=holdout_limit,
                    rng=holdout_rng,
                )
            else:
                train_seen += 1
                _reservoir_add(
                    train,
                    row,
                    seen=train_seen,
                    limit=train_limit,
                    rng=train_rng,
                )
    return train, holdout, train_seen, holdout_seen, excluded


def _load_synthetic(path: Path) -> list[PublicRentTrainingRow]:
    with path.open(encoding="utf-8") as handle:
        return [
            row
            for line in handle
            if _eligible(row := PublicRentTrainingRow.model_validate_json(line))
        ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matrix(rows: list[PublicRentTrainingRow], reference: PeerReference) -> np.ndarray:
    return np.asarray([deposit_model_vector(row, reference) for row in rows], dtype=float)


def _new_model(*, quantile: float, seed: int) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        (
            "model",
            HistGradientBoostingRegressor(
                loss="quantile",
                quantile=quantile,
                learning_rate=.06,
                max_iter=250,
                max_leaf_nodes=31,
                min_samples_leaf=30,
                l2_regularization=.2,
                early_stopping=True,
                validation_fraction=.1,
                n_iter_no_change=20,
                random_state=seed,
            ),
        ),
    ])


def _predict(
    rows: list[PublicRentTrainingRow],
    matrix: np.ndarray,
    models: dict[str, dict[str, Pipeline]],
) -> tuple[np.ndarray, np.ndarray]:
    p50 = np.empty(len(rows), dtype=float)
    p95 = np.empty(len(rows), dtype=float)
    for mode, mode_models in models.items():
        indexes = np.asarray(
            [index for index, row in enumerate(rows) if rent_mode(row) == mode],
            dtype=int,
        )
        if indexes.size == 0:
            continue
        p50[indexes] = mode_models["p50"].predict(matrix[indexes])
        p95[indexes] = mode_models["p95"].predict(matrix[indexes])
    return p50, np.maximum(p50, p95)


def _actual_deposits(rows: list[PublicRentTrainingRow]) -> np.ndarray:
    return np.asarray([row.features.deposit_million_won for row in rows], dtype=float)


def _total_predictions(
    rows: list[PublicRentTrainingRow],
    log_density_predictions: np.ndarray,
) -> np.ndarray:
    return np.asarray(
        [
            predicted_deposit_million_won(row, prediction)
            for row, prediction in zip(rows, log_density_predictions, strict=True)
        ],
        dtype=float,
    )


def main() -> int:
    args = parse_args()
    if args.holdout_months < 1:
        raise SystemExit("--holdout-months는 1 이상이어야 합니다.")
    input_path = args.input.resolve()
    synthetic_path = args.synthetic.resolve()
    model_output = args.model_output.resolve()
    report_output = args.report_output.resolve()
    for path in (input_path, synthetic_path):
        if not path.exists():
            raise SystemExit(f"입력 파일이 없습니다: {path}")
    for path in (model_output, report_output):
        if path.exists() and not args.force:
            raise SystemExit(f"이미 출력이 있습니다: {path} (--force로 교체)")

    periods = _load_periods(input_path)
    if len(periods) <= args.holdout_months:
        raise SystemExit("시간 분할에 필요한 계약월이 부족합니다.")
    holdout_periods = set(periods[-args.holdout_months:])
    train, holdout, train_seen, holdout_seen, excluded = _load_split(
        input_path,
        holdout_periods=holdout_periods,
        train_limit=args.max_train,
        holdout_limit=args.max_holdout,
        seed=args.seed,
    )
    synthetic = _load_synthetic(synthetic_path)
    if not train or not holdout or not synthetic:
        raise SystemExit("학습·홀드아웃·합성 데이터가 모두 필요합니다.")

    # Trim only the training sample. Thresholds are learned without seeing holdout.
    trim_bounds: dict[str, tuple[float, float]] = {}
    for mode in ("jeonse", "monthly"):
        values = np.asarray(
            [deposit_target(row) for row in train if rent_mode(row) == mode],
            dtype=float,
        )
        trim_bounds[mode] = (
            float(np.percentile(values, .1)),
            float(np.percentile(values, 99.9)),
        )
    train_before_trim = len(train)
    train = [
        row
        for row in train
        if trim_bounds[rent_mode(row)][0]
        <= deposit_target(row)
        <= trim_bounds[rent_mode(row)][1]
    ]

    peer_reference = build_peer_reference(train)
    train_matrix = _matrix(train, peer_reference)
    holdout_matrix = _matrix(holdout, peer_reference)
    synthetic_matrix = _matrix(synthetic, peer_reference)
    train_targets = np.asarray([deposit_target(row) for row in train], dtype=float)
    models: dict[str, dict[str, Pipeline]] = {}
    training_rows_by_mode: dict[str, int] = {}
    print(
        f"학습: 실제 {len(train):,}건 (후보 {train_seen:,}건, 극단값 {train_before_trim - len(train):,}건 제외)",
        flush=True,
    )
    for mode_index, mode in enumerate(("jeonse", "monthly")):
        indexes = np.asarray(
            [index for index, row in enumerate(train) if rent_mode(row) == mode],
            dtype=int,
        )
        if indexes.size < 100:
            raise SystemExit(f"{mode} 학습 데이터가 부족합니다: {indexes.size}건")
        mode_models = {
            "p50": _new_model(quantile=.5, seed=args.seed + mode_index * 10),
            "p95": _new_model(quantile=.95, seed=args.seed + mode_index * 10 + 1),
        }
        for name, model in mode_models.items():
            print(f"{mode} {name} 학습 중 ({indexes.size:,}건)", flush=True)
            model.fit(train_matrix[indexes], train_targets[indexes])
        models[mode] = mode_models
        training_rows_by_mode[mode] = int(indexes.size)

    holdout_p50_log, holdout_p95_log = _predict(holdout, holdout_matrix, models)
    synthetic_p50_log, synthetic_p95_log = _predict(synthetic, synthetic_matrix, models)
    holdout_actual = _actual_deposits(holdout)
    synthetic_actual = _actual_deposits(synthetic)
    holdout_p50 = _total_predictions(holdout, holdout_p50_log)
    holdout_p95 = _total_predictions(holdout, holdout_p95_log)
    synthetic_p50 = _total_predictions(synthetic, synthetic_p50_log)
    synthetic_p95 = _total_predictions(synthetic, synthetic_p95_log)
    holdout_flags = holdout_actual > holdout_p95
    synthetic_flags = synthetic_actual > synthetic_p95

    scenario_totals: Counter[str] = Counter()
    scenario_detected: Counter[str] = Counter()
    for row, detected in zip(synthetic, synthetic_flags, strict=True):
        scenario = row.synthetic_scenario or "unknown"
        scenario_totals[scenario] += 1
        scenario_detected[scenario] += bool(detected)

    trained_at = datetime.now(timezone.utc).isoformat()
    artifact = {
        "schema_version": "deposit-quantile-model-1.0",
        "trained_at": trained_at,
        "models": models,
        "peer_reference": peer_reference,
        "features": DEPOSIT_MODEL_FEATURES,
        "target": "log1p(deposit_per_m2_million_won)",
        "training_periods": [period for period in periods if period not in holdout_periods],
        "holdout_periods": sorted(holdout_periods),
        "training_trim_log_density_bounds": trim_bounds,
    }
    absolute_percentage_error = np.abs(holdout_actual - holdout_p50) / holdout_actual
    report = {
        "schema_version": "deposit-quantile-report-1.0",
        "trained_at": trained_at,
        "library": {"scikit_learn": sklearn.__version__},
        "data": {
            "source_sha256": _sha256(input_path),
            "eligible_rows": train_seen + holdout_seen,
            "excluded_ineligible_rows": excluded,
            "train_candidates": train_seen,
            "train_sampled_before_trim": train_before_trim,
            "train_sampled": len(train),
            "train_sampled_by_rent_mode": training_rows_by_mode,
            "holdout_candidates": holdout_seen,
            "holdout_sampled": len(holdout),
            "holdout_periods": sorted(holdout_periods),
            "synthetic_rows": len(synthetic),
        },
        "evaluation": {
            "public_holdout_p50_mae_million_won": round(
                float(np.mean(np.abs(holdout_actual - holdout_p50))),
                6,
            ),
            "public_holdout_p50_median_absolute_percentage_error": round(
                float(np.median(absolute_percentage_error)),
                6,
            ),
            "public_holdout_p95_coverage": round(float(np.mean(~holdout_flags)), 6),
            "public_holdout_flag_rate": round(float(np.mean(holdout_flags)), 6),
            "synthetic_detection_rate": round(float(np.mean(synthetic_flags)), 6),
            "synthetic_detection_by_scenario": {
                scenario: round(scenario_detected[scenario] / total, 6)
                for scenario, total in sorted(scenario_totals.items())
            },
            "synthetic_p95_excess_ratio_median": round(
                float(np.median(synthetic_actual / np.maximum(synthetic_p95, 1e-6))),
                6,
            ),
        },
        "interpretation": {
            "p50": "유사 계약 조건에서 예상되는 보증금 중앙값",
            "p95": "유사 계약 100건 중 약 95건이 이 값 이하일 것으로 보는 상한",
            "flag": "입력 보증금이 예측 p95를 초과한 경우의 시장 이상 조건 신호",
        },
        "limitations": [
            "공공 신고자료는 정상/사고 라벨이 아니므로 시장 범위를 학습하는 용도입니다.",
            "합성 탐지율은 모델 배관 시험 지표이며 실제 보증사고 탐지 정확도가 아닙니다.",
            "보증금 시장 이상 신호는 근저당과 시세 대비 총부담 규칙을 대체하지 않습니다.",
        ],
    }

    model_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    model_temp = model_output.with_suffix(model_output.suffix + ".tmp")
    report_temp = report_output.with_suffix(report_output.suffix + ".tmp")
    try:
        joblib.dump(artifact, model_temp)
        report_temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(model_temp, model_output)
        os.replace(report_temp, report_output)
    finally:
        for path in (model_temp, report_temp):
            if path.exists():
                path.unlink()

    evaluation = report["evaluation"]
    print(f"홀드아웃 p50 중앙 절대비율오차: {evaluation['public_holdout_p50_median_absolute_percentage_error']:.2%}")
    print(f"홀드아웃 p95 포함률: {evaluation['public_holdout_p95_coverage']:.2%}")
    print(f"합성 보증금 이상 조건 탐지율: {evaluation['synthetic_detection_rate']:.2%}")
    for scenario, rate in evaluation["synthetic_detection_by_scenario"].items():
        print(f"  {scenario}: {rate:.2%}")
    print(f"모델: {model_output}")
    print(f"리포트: {report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
