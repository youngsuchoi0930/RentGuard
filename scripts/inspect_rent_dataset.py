from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ml_schemas import PublicRentTrainingRow  # noqa: E402


FORBIDDEN_FIELDS = {"jibun", "building_name", "mhouseNm", "owner", "raw_text", "address"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전월세 ML JSONL의 스키마와 비식별 상태를 검사합니다.")
    parser.add_argument("path", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.path.resolve()
    if not path.exists():
        raise SystemExit(f"파일이 없습니다: {path}")

    rows = duplicates = missing_age = 0
    ids: set[str] = set()
    districts: Counter[str] = Counter()
    labels: Counter[str] = Counter()
    scenarios: Counter[str] = Counter()
    deposit_range = [float("inf"), float("-inf")]
    rent_range = [float("inf"), float("-inf")]

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                payload = json.loads(line)
                row = PublicRentTrainingRow.model_validate(payload)
            except (json.JSONDecodeError, ValueError) as exc:
                raise SystemExit(f"{line_number}번째 행 검증 실패: {exc}") from exc
            feature_names = set(payload.get("features", {}))
            leaked = feature_names & FORBIDDEN_FIELDS
            if leaked:
                raise SystemExit(f"금지된 상세 위치/원문 필드 발견: {sorted(leaked)}")
            rows += 1
            duplicates += row.sample_id in ids
            ids.add(row.sample_id)
            features = row.features
            districts[features.district_name] += 1
            labels[row.label] += 1
            scenarios[row.synthetic_scenario or "none"] += 1
            missing_age += features.building_age_years is None
            deposit_range[0] = min(deposit_range[0], features.deposit_million_won)
            deposit_range[1] = max(deposit_range[1], features.deposit_million_won)
            rent_range[0] = min(rent_range[0], features.monthly_rent_million_won)
            rent_range[1] = max(rent_range[1], features.monthly_rent_million_won)

    print(f"행: {rows:,}")
    print(f"파일 크기: {path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"지역: {len(districts)}개")
    print(f"라벨: {dict(labels)}")
    print(f"합성 시나리오: {dict(scenarios)}")
    print(f"건축연식 미확인: {missing_age:,}건")
    print(f"보증금 범위(백만원): {deposit_range[0]:g}~{deposit_range[1]:g}")
    print(f"월세 범위(백만원): {rent_range[0]:g}~{rent_range[1]:g}")
    print(f"중복 sample_id: {duplicates:,}건")
    print("금지 필드: 없음")
    return 1 if duplicates else 0


if __name__ == "__main__":
    raise SystemExit(main())
