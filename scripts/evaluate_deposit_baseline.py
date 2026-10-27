"""Compare the trusted v2 artifact with a training-only peer-median baseline.

Writes aggregate metrics only. Does not train or replace a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import train_deposit_quantile as training
import numpy as np

from app.config import Settings
from app.ml_schemas import PublicRentTrainingRow
from app.services.deposit_predictor import _load_configured_artifact
from app.services.market_anomaly_features import peer_stat, rent_mode


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=training.ROOT / "data/ml/seoul-rh-rent-market-v1.jsonl")
    parser.add_argument("--report", type=Path, default=training.ROOT / "data/ml/deposit-quantile-v2-report.json")
    parser.add_argument("--model", type=Path, default=training.ROOT / "models/deposit-quantile-v2.joblib")
    parser.add_argument("--output", type=Path, default=training.ROOT / "docs/evaluation/deposit-baseline.json")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    source_hash = training._sha256(args.input)
    if source_hash != report["data"]["source_sha256"]:
        raise SystemExit("Dataset hash differs from the recorded v2 evaluation.")
    _, artifact, integrity = _load_configured_artifact(Settings(
        deposit_model_path=str(args.model.resolve()), require_deposit_model=True,
    ))
    periods = set(artifact["holdout_periods"])
    rows = []
    with args.input.open(encoding="utf-8") as handle:
        for line in handle:
            payload = json.loads(line)
            features = payload["features"]
            period = features["contract_year"] * 100 + features["contract_month"]
            if period in periods:
                row = PublicRentTrainingRow.model_validate(payload)
                if training._eligible(row):
                    rows.append(row)
    if len(rows) != report["data"]["holdout_sampled"]:
        raise SystemExit("Holdout row count differs from the recorded evaluation.")
    reference = artifact["peer_reference"]
    actual = training._actual_deposits(rows)
    baseline = np.asarray([
        math.expm1(peer_stat(row, reference).deposit_log_median) * row.features.exclusive_area_m2
        for row in rows
    ])
    p50_log, p95_log = training._predict(
        rows,
        training._matrix(rows, reference, version="v2"),
        training._matrix(rows, reference, version="v1"),
        artifact["models"],
        artifact["calibration_log_offsets"],
    )
    p50 = training._total_predictions(rows, p50_log)
    p95 = training._total_predictions(rows, p95_log)
    metrics = {}
    for mode in ("all", "jeonse", "monthly"):
        selected = np.asarray([mode == "all" or rent_mode(row) == mode for row in rows])
        truth, simple, predicted = actual[selected], baseline[selected], p50[selected]
        baseline_mae = float(np.mean(np.abs(truth - simple)))
        model_mae = float(np.mean(np.abs(truth - predicted)))
        metrics[mode] = {
            "rows": int(selected.sum()),
            "baseline_mae_million_won": round(baseline_mae, 6),
            "model_mae_million_won": round(model_mae, 6),
            "baseline_median_absolute_percentage_error": round(float(np.median(np.abs(truth - simple) / truth)), 6),
            "model_median_absolute_percentage_error": round(float(np.median(np.abs(truth - predicted) / truth)), 6),
            "mae_reduction_fraction": round(1 - model_mae / baseline_mae, 6),
            "model_p95_coverage": round(float(np.mean(truth <= p95[selected])), 6),
        }
    recorded = report["evaluation"]["public_holdout_p50_mae_million_won"]
    if abs(metrics["all"]["model_mae_million_won"] - recorded) > 0.00001:
        raise SystemExit("Persisted model metrics differ from the recorded evaluation.")
    output = {
        "schema_version": "deposit-baseline-evaluation-1.0",
        "evaluation_kind": "retrospective_comparison_on_existing_holdout",
        "source_sha256": source_hash,
        "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "model_integrity": integrity,
        "holdout_periods": sorted(periods),
        "baseline": {
            "method": "training-only peer median deposit per m2 multiplied by target area",
            "group_fallback": ["district/legal-dong/10m2-band/rent-mode", "district/10m2-band/rent-mode", "district/rent-mode", "rent-mode"],
            "minimum_group_rows": [20, 40, 80, 1],
            "reference": "same peer_reference stored in the v2 artifact; no holdout targets",
        },
        "metrics": metrics,
        "limitations": [
            "Existing historical holdout reused for comparison; this is not a new untouched evaluation set.",
            "Baseline does not explicitly adjust for monthly-rent amount, age or floor.",
            "Overall coverage does not establish conditional coverage or fraud detection performance.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"Aggregate report: {args.output}")


if __name__ == "__main__":
    main()
