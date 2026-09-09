from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.ml_schemas import PublicRentTrainingRow  # noqa: E402
from app.services.synthetic_rent_data import make_synthetic_anomaly  # noqa: E402


SCENARIOS = ("deposit_spike", "rent_spike", "renewal_jump")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공공 전월세 행을 기반으로 시험용 이상 조건을 만듭니다.")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "data" / "ml" / "seoul-rh-rent-market-v1.jsonl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "ml" / "seoul-rh-rent-synthetic-v1.jsonl",
    )
    parser.add_argument("--count", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def _reservoir_sample(path: Path, count: int, rng: random.Random) -> list[PublicRentTrainingRow]:
    reservoir: list[PublicRentTrainingRow] = []
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            row = PublicRentTrainingRow.model_validate(json.loads(line))
            if index < count:
                reservoir.append(row)
                continue
            replacement = rng.randint(0, index)
            if replacement < count:
                reservoir[replacement] = row
    return reservoir


def main() -> int:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count는 1 이상이어야 합니다.")
    source = args.input.resolve()
    output = args.output.resolve()
    if not source.exists():
        raise SystemExit(f"입력 파일이 없습니다: {source}")
    if output.exists() and not args.force:
        raise SystemExit(f"이미 파일이 있습니다: {output} (--force로 교체)")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output.with_suffix(output.suffix + ".tmp")

    selected = _reservoir_sample(source, args.count, random.Random(args.seed))
    if len(selected) < args.count:
        raise SystemExit(f"입력 행이 부족합니다: 요청 {args.count:,}건, 입력 {len(selected):,}건")
    try:
        with temp_output.open("w", encoding="utf-8", newline="\n") as handle:
            for index, row in enumerate(selected):
                synthetic = make_synthetic_anomaly(
                    row,
                    scenario=SCENARIOS[index % len(SCENARIOS)],
                    seed=args.seed + index,
                )
                handle.write(synthetic.model_dump_json() + "\n")
        os.replace(temp_output, output)
    finally:
        if temp_output.exists():
            temp_output.unlink()

    print(f"완료: 합성 이상 조건 {len(selected):,}건", flush=True)
    print(f"출력: {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
