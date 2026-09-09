from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.rent_data_collector import (  # noqa: E402
    SEOUL_DISTRICTS,
    iter_rent_batches,
    months_through,
    recent_complete_months,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="국토부 연립·다세대 전월세 자료를 비식별 ML JSONL로 수집합니다.",
    )
    parser.add_argument(
        "--district",
        action="append",
        default=[],
        help="서울 시군구 코드. 여러 번 지정 가능하며 생략하면 25개 구 전체를 수집합니다.",
    )
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--through", help="마지막 계약월 YYYYMM. 생략하면 직전 완료 월입니다.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "ml" / "seoul-rh-rent-market-v1.jsonl",
    )
    parser.add_argument("--force", action="store_true", help="기존 출력 파일을 교체합니다.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.months < 1 or args.months > 60:
        raise SystemExit("--months는 1~60 사이여야 합니다.")
    districts = args.district or list(SEOUL_DISTRICTS)
    unknown = sorted(set(districts) - set(SEOUL_DISTRICTS))
    if unknown:
        raise SystemExit(f"지원하지 않는 서울 시군구 코드: {', '.join(unknown)}")
    months = months_through(args.through, args.months) if args.through else recent_complete_months(args.months)

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and not args.force:
        raise SystemExit(f"이미 파일이 있습니다: {output} (--force로 교체)")
    temp_output = output.with_suffix(output.suffix + ".tmp")

    print(
        f"수집 시작: 서울 {len(districts)}개 구, {months[0]}~{months[-1]} "
        f"({len(months)}개월)",
        flush=True,
    )
    requests = received = written = skipped = 0
    seen_ids: set[str] = set()
    active_district: str | None = None
    district_written = 0
    try:
        with temp_output.open("w", encoding="utf-8", newline="\n") as handle:
            for batch in iter_rent_batches(district_codes=districts, months=months):
                if active_district is not None and batch.district_code != active_district:
                    print(
                        f"  {SEOUL_DISTRICTS[active_district]} 완료: {district_written:,}건",
                        flush=True,
                    )
                    district_written = 0
                active_district = batch.district_code
                requests += 1
                received += len(batch.rows)
                for row in batch.rows:
                    if row.sample_id in seen_ids:
                        skipped += 1
                        continue
                    seen_ids.add(row.sample_id)
                    handle.write(row.model_dump_json() + "\n")
                    written += 1
                    district_written += 1
            if active_district is not None:
                print(
                    f"  {SEOUL_DISTRICTS[active_district]} 완료: {district_written:,}건",
                    flush=True,
                )
        os.replace(temp_output, output)
    finally:
        if temp_output.exists():
            temp_output.unlink()

    print(
        f"완료: {written:,}건 저장, {requests:,}회 요청, "
        f"중복 {skipped:,}건 제외 (수신 {received:,}건)",
        flush=True,
    )
    print(f"출력: {output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
