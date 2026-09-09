from __future__ import annotations

import argparse
import hashlib
import json
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
from sklearn.ensemble import IsolationForest  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from app.ml_schemas import PublicRentTrainingRow  # noqa: E402
from app.services.market_anomaly_features import (  # noqa: E402
    NUMERIC_FEATURES,
    PeerReference,
    build_peer_reference,
    model_vector,
    rent_mode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="서울 연립·다세대 전월세 이상치 기준 모델을 학습합니다.")
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
        default=ROOT / "models" / "market-anomaly-v1.joblib",
    )
    parser.add_argument(
        "--report-output",
        type=Path,
        default=ROOT / "data" / "ml" / "market-anomaly-v1-report.json",
    )
    parser.add_argument("--max-train", type=int, default=100_000)
    parser.add_argument("--max-holdout", type=int, default=50_000)
    parser.add_argument("--holdout-months", type=int, default=3)
    parser.add_argument("--contamination", type=float, default=.02)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _period(row: PublicRentTrainingRow) -> int:
    return row.features.contract_year * 100 + row.features.contract_month


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
            periods.add(_period(row))
    return sorted(periods)


def _load_split(
    path: Path,
    *,
    holdout_periods: set[int],
    train_limit: int,
    holdout_limit: int,
    seed: int,
) -> tuple[list[PublicRentTrainingRow], list[PublicRentTrainingRow], int, int]:
    train: list[PublicRentTrainingRow] = []
    holdout: list[PublicRentTrainingRow] = []
    train_seen = holdout_seen = 0
    train_rng = random.Random(seed)
    holdout_rng = random.Random(seed + 1)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            row = PublicRentTrainingRow.model_validate_json(line)
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
    return train, holdout, train_seen, holdout_seen


def _load_synthetic(path: Path) -> list[PublicRentTrainingRow]:
    with path.open(encoding="utf-8") as handle:
        return [PublicRentTrainingRow.model_validate_json(line) for line in handle]


def _matrix(rows: list[PublicRentTrainingRow], reference: PeerReference) -> np.ndarray:
    return np.asarray([model_vector(row, reference) for row in rows], dtype=float)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _new_pipeline(*, contamination: float, seed: int) -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        (
            "model",
            IsolationForest(
                n_estimators=200,
                max_samples=4096,
                contamination=contamination,
                random_state=seed,
                n_jobs=-1,
            ),
        ),
    ])


def _predict_grouped(
    rows: list[PublicRentTrainingRow],
    matrix: np.ndarray,
    pipelines: dict[str, Pipeline],
) -> tuple[np.ndarray, np.ndarray]:
    predictions = np.empty(len(rows), dtype=int)
    scores = np.empty(len(rows), dtype=float)
    for mode, pipeline in pipelines.items():
        indexes = np.asarray(
            [index for index, row in enumerate(rows) if rent_mode(row) == mode],
            dtype=int,
        )
        if indexes.size == 0:
            continue
        predictions[indexes] = pipeline.predict(matrix[indexes])
        scores[indexes] = pipeline.decision_function(matrix[indexes])
    return predictions, scores


def main() -> int:
    args = parse_args()
    if not 0 < args.contamination < .5:
        raise SystemExit("--contamination은 0과 0.5 사이여야 합니다.")
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
    train, holdout, train_seen, holdout_seen = _load_split(
        input_path,
        holdout_periods=holdout_periods,
        train_limit=args.max_train,
        holdout_limit=args.max_holdout,
        seed=args.seed,
    )
    synthetic = _load_synthetic(synthetic_path)
    if not train or not holdout or not synthetic:
        raise SystemExit("학습·홀드아웃·합성 데이터가 모두 필요합니다.")

    peer_reference = build_peer_reference(train)
    print(f"학습: 실제 {len(train):,}건 (전체 후보 {train_seen:,}건)", flush=True)
    train_matrix = _matrix(train, peer_reference)
    holdout_matrix = _matrix(holdout, peer_reference)
    synthetic_matrix = _matrix(synthetic, peer_reference)
    pipelines: dict[str, Pipeline] = {}
    training_rows_by_mode: dict[str, int] = {}
    for mode_index, mode in enumerate(("jeonse", "monthly")):
        indexes = np.asarray(
            [index for index, row in enumerate(train) if rent_mode(row) == mode],
            dtype=int,
        )
        if indexes.size < 100:
            raise SystemExit(f"{mode} 학습 데이터가 부족합니다: {indexes.size}건")
        pipeline = _new_pipeline(
            contamination=args.contamination,
            seed=args.seed + mode_index,
        )
        pipeline.fit(train_matrix[indexes])
        pipelines[mode] = pipeline
        training_rows_by_mode[mode] = int(indexes.size)
    holdout_predictions, holdout_scores = _predict_grouped(
        holdout,
        holdout_matrix,
        pipelines,
    )
    synthetic_predictions, synthetic_scores = _predict_grouped(
        synthetic,
        synthetic_matrix,
        pipelines,
    )

    scenario_totals: Counter[str] = Counter()
    scenario_detected: Counter[str] = Counter()
    for row, prediction in zip(synthetic, synthetic_predictions, strict=True):
        scenario = row.synthetic_scenario or "unknown"
        scenario_totals[scenario] += 1
        scenario_detected[scenario] += prediction == -1

    artifact = {
        "schema_version": "market-anomaly-model-1.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "pipelines": pipelines,
        "peer_reference": peer_reference,
        "numeric_features": NUMERIC_FEATURES,
        "training_periods": [period for period in periods if period not in holdout_periods],
        "holdout_periods": sorted(holdout_periods),
        "contamination": args.contamination,
    }
    report = {
        "schema_version": "market-anomaly-report-1.0",
        "trained_at": artifact["trained_at"],
        "library": {"scikit_learn": sklearn.__version__},
        "data": {
            "source_sha256": _sha256(input_path),
            "source_rows": train_seen + holdout_seen,
            "train_candidates": train_seen,
            "train_sampled": len(train),
            "train_sampled_by_rent_mode": training_rows_by_mode,
            "holdout_candidates": holdout_seen,
            "holdout_sampled": len(holdout),
            "holdout_periods": sorted(holdout_periods),
            "synthetic_rows": len(synthetic),
        },
        "evaluation": {
            "public_holdout_flag_rate": round(float(np.mean(holdout_predictions == -1)), 6),
            "synthetic_detection_rate": round(float(np.mean(synthetic_predictions == -1)), 6),
            "synthetic_detection_by_scenario": {
                scenario: round(scenario_detected[scenario] / total, 6)
                for scenario, total in sorted(scenario_totals.items())
            },
            "holdout_score_percentiles": {
                str(percentile): round(float(np.percentile(holdout_scores, percentile)), 6)
                for percentile in (1, 5, 50, 95, 99)
            },
            "synthetic_score_percentiles": {
                str(percentile): round(float(np.percentile(synthetic_scores, percentile)), 6)
                for percentile in (1, 5, 50, 95, 99)
            },
        },
        "limitations": [
            "공공데이터는 정상 라벨이 아니라 신고된 시장 거래의 기준 분포입니다.",
            "합성 탐지율은 파이프라인 시험 지표이며 실제 위험 탐지 정확도가 아닙니다.",
            "근저당·소유권·실제 보증사고는 이 시장 이상치 모델의 입력에 포함되지 않습니다.",
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

    print(f"공공 홀드아웃 이상치 비율: {report['evaluation']['public_holdout_flag_rate']:.2%}")
    print(f"합성 이상 조건 탐지율: {report['evaluation']['synthetic_detection_rate']:.2%}")
    print(f"모델: {model_output}")
    print(f"리포트: {report_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
