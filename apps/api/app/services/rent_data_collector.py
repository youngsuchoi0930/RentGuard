from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import date
from typing import Iterable
from xml.etree import ElementTree

import httpx

from ..config import Settings, get_settings
from ..ml_schemas import PublicRentFeatureVector, PublicRentTrainingRow
from .public_data import PublicAPIError, _secret_value


RENT_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent"

SEOUL_DISTRICTS: dict[str, str] = {
    "11110": "종로구",
    "11140": "중구",
    "11170": "용산구",
    "11200": "성동구",
    "11215": "광진구",
    "11230": "동대문구",
    "11260": "중랑구",
    "11290": "성북구",
    "11305": "강북구",
    "11320": "도봉구",
    "11350": "노원구",
    "11380": "은평구",
    "11410": "서대문구",
    "11440": "마포구",
    "11470": "양천구",
    "11500": "강서구",
    "11530": "구로구",
    "11545": "금천구",
    "11560": "영등포구",
    "11590": "동작구",
    "11620": "관악구",
    "11650": "서초구",
    "11680": "강남구",
    "11710": "송파구",
    "11740": "강동구",
}


@dataclass(frozen=True)
class CollectionStats:
    requests: int
    received: int
    written: int
    skipped: int


@dataclass(frozen=True)
class RentBatch:
    district_code: str
    district_name: str
    deal_month: str
    page: int
    rows: tuple[PublicRentTrainingRow, ...]


def recent_complete_months(count: int, *, today: date | None = None) -> list[str]:
    if count < 1:
        raise ValueError("수집 개월 수는 1 이상이어야 합니다.")
    current = today or date.today()
    year, month = current.year, current.month - 1
    if month == 0:
        year, month = year - 1, 12
    result: list[str] = []
    for _ in range(count):
        result.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(result))


def months_through(through: str, count: int) -> list[str]:
    if len(through) != 6 or not through.isdigit() or not 1 <= int(through[4:]) <= 12:
        raise ValueError("기준 월은 YYYYMM 형식이어야 합니다.")
    year, month = int(through[:4]), int(through[4:])
    result: list[str] = []
    for _ in range(count):
        result.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(result))


def _number(value: str | None, *, integer: bool = False) -> float | int | None:
    cleaned = (value or "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return int(float(cleaned)) if integer else float(cleaned)
    except ValueError:
        return None


def _contract_type(value: str | None) -> str:
    normalized = (value or "").strip()
    if "신규" in normalized:
        return "new"
    if "갱신" in normalized:
        return "renewal"
    return "unknown"


def _yes_no(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in {"사용", "y", "yes", "1"}:
        return "yes"
    if normalized in {"미사용", "n", "no", "0"}:
        return "no"
    return "unknown"


def _change_ratio(current: int, previous: int | None) -> float | None:
    if previous is None or previous <= 0:
        return None
    return round((current - previous) / previous, 6)


def _sample_id(
    item: ElementTree.Element,
    *,
    district_code: str,
    page: int,
    position: int,
) -> str:
    # Location participates only in the digest for deduplication and is never emitted.
    raw = "|".join((child.tag + "=" + (child.text or "").strip()) for child in item)
    raw = f"{district_code}|{page}|{position}|{raw}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def parse_rent_item(
    item: ElementTree.Element,
    *,
    district_code: str,
    district_name: str,
    page: int = 1,
    position: int = 0,
) -> PublicRentTrainingRow | None:
    area = _number(item.findtext("excluUseAr"))
    deposit_10k = _number(item.findtext("deposit"), integer=True)
    rent_10k = _number(item.findtext("monthlyRent"), integer=True)
    year = _number(item.findtext("dealYear"), integer=True)
    month = _number(item.findtext("dealMonth"), integer=True)
    if area is None or area <= 0 or deposit_10k is None or rent_10k is None or year is None or month is None:
        return None

    build_year = _number(item.findtext("buildYear"), integer=True)
    floor = _number(item.findtext("floor"), integer=True)
    previous_deposit_10k = _number(item.findtext("preDeposit"), integer=True)
    previous_rent_10k = _number(item.findtext("preMonthlyRent"), integer=True)
    deposit_won = int(deposit_10k) * 10_000
    rent_won = int(rent_10k) * 10_000
    area_value = float(area)

    return PublicRentTrainingRow(
        sample_id=_sample_id(
            item,
            district_code=district_code,
            page=page,
            position=position,
        ),
        source_kind="public_transaction",
        features=PublicRentFeatureVector(
            district_code=district_code,
            district_name=district_name,
            legal_dong_name=(item.findtext("umdNm") or "미상").strip() or "미상",
            contract_year=int(year),
            contract_month=int(month),
            exclusive_area_m2=area_value,
            floor=int(floor) if floor is not None else None,
            building_age_years=(
                max(0, int(year) - int(build_year))
                if build_year is not None and int(build_year) <= int(year)
                else None
            ),
            deposit_million_won=round(deposit_won / 1_000_000, 6),
            monthly_rent_million_won=round(rent_won / 1_000_000, 6),
            deposit_per_m2_million_won=round(deposit_won / 1_000_000 / area_value, 6),
            monthly_rent_per_m2_million_won=round(rent_won / 1_000_000 / area_value, 6),
            contract_type=_contract_type(item.findtext("contractType")),
            renewal_right_used=_yes_no(item.findtext("useRRRight")),
            previous_deposit_million_won=(
                round(int(previous_deposit_10k) / 100, 6)
                if previous_deposit_10k is not None
                else None
            ),
            previous_monthly_rent_million_won=(
                round(int(previous_rent_10k) / 100, 6)
                if previous_rent_10k is not None
                else None
            ),
            deposit_change_ratio=_change_ratio(int(deposit_10k), previous_deposit_10k),
            monthly_rent_change_ratio=_change_ratio(int(rent_10k), previous_rent_10k),
        ),
    )


def parse_rent_payload(
    payload: bytes,
    *,
    district_code: str,
    district_name: str,
    page: int = 1,
) -> tuple[list[PublicRentTrainingRow], int]:
    root = ElementTree.fromstring(payload)
    result_code = root.findtext(".//resultCode")
    if result_code != "000":
        message = root.findtext(".//resultMsg") or "공공데이터 응답 오류"
        raise PublicAPIError(f"전월세 API 오류 {result_code}: {message}")
    rows = [
        parsed
        for position, item in enumerate(root.findall(".//item"))
        if (parsed := parse_rent_item(
            item,
            district_code=district_code,
            district_name=district_name,
            page=page,
            position=position,
        )) is not None
    ]
    total_count = int(root.findtext(".//totalCount") or len(rows))
    return rows, total_count


def _get_with_retry(
    client: httpx.Client,
    *,
    params: dict[str, str | int],
    attempts: int = 3,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = client.get(RENT_URL, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1.5 * (attempt + 1))
    raise PublicAPIError("전월세 공공데이터 호출에 실패했습니다.") from last_error


def iter_rent_batches(
    *,
    district_codes: Iterable[str],
    months: Iterable[str],
    settings: Settings | None = None,
    page_size: int = 1000,
    request_delay_seconds: float = 0.05,
) -> Iterable[RentBatch]:
    config = settings or get_settings()
    key = _secret_value(config.data_go_kr_service_key)
    if not key:
        raise PublicAPIError("DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다.")

    with httpx.Client(timeout=config.public_api_timeout_seconds) as client:
        for district_code in district_codes:
            if district_code not in SEOUL_DISTRICTS:
                raise ValueError(f"지원하지 않는 서울 시군구 코드입니다: {district_code}")
            district_name = SEOUL_DISTRICTS[district_code]
            for deal_month in months:
                page = 1
                while True:
                    payload = _get_with_retry(
                        client,
                        params={
                            "serviceKey": key,
                            "LAWD_CD": district_code,
                            "DEAL_YMD": deal_month,
                            "numOfRows": page_size,
                            "pageNo": page,
                        },
                    )
                    rows, total_count = parse_rent_payload(
                        payload,
                        district_code=district_code,
                        district_name=district_name,
                        page=page,
                    )
                    yield RentBatch(
                        district_code=district_code,
                        district_name=district_name,
                        deal_month=deal_month,
                        page=page,
                        rows=tuple(rows),
                    )
                    if page * page_size >= total_count:
                        break
                    page += 1
                    if request_delay_seconds:
                        time.sleep(request_delay_seconds)
                if request_delay_seconds:
                    time.sleep(request_delay_seconds)



def collect_rent_rows(
    *,
    district_codes: Iterable[str],
    months: Iterable[str],
    settings: Settings | None = None,
    page_size: int = 1000,
    request_delay_seconds: float = 0.05,
) -> tuple[list[PublicRentTrainingRow], CollectionStats]:
    """Collect into memory for small jobs and tests; the CLI streams batches to disk."""
    all_rows: dict[str, PublicRentTrainingRow] = {}
    requests = received = skipped = 0
    for batch in iter_rent_batches(
        district_codes=district_codes,
        months=months,
        settings=settings,
        page_size=page_size,
        request_delay_seconds=request_delay_seconds,
    ):
        requests += 1
        received += len(batch.rows)
        for row in batch.rows:
            if row.sample_id in all_rows:
                skipped += 1
            else:
                all_rows[row.sample_id] = row
    return list(all_rows.values()), CollectionStats(
        requests=requests,
        received=received,
        written=len(all_rows),
        skipped=skipped,
    )
