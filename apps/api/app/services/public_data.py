from __future__ import annotations

import asyncio
import math
import re
import statistics
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import unquote
from xml.etree import ElementTree

import httpx

from ..config import Settings, get_settings
from ..schemas import AddressSuggestion


JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
BUILDING_TITLE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"
BUILDING_AREA_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo"
TRADE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"


class PublicAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResolvedAddress:
    road_address: str
    jibun_address: str
    zip_code: str
    building_name: str | None
    adm_code: str
    legal_dong_name: str
    mountain: bool
    lot_main: int
    lot_sub: int

    @property
    def sigungu_code(self) -> str:
        return self.adm_code[:5]

    @property
    def bjdong_code(self) -> str:
        return self.adm_code[5:10]

    @property
    def jibun(self) -> str:
        suffix = f"-{self.lot_sub}" if self.lot_sub else ""
        return f"{self.lot_main}{suffix}"


@dataclass(frozen=True)
class OfficialBuilding:
    status: str
    address: str | None = None
    main_use: str | None = None
    approval_date: str | None = None
    exclusive_area: float | None = None
    is_illegal_building: bool | None = None
    message: str | None = None


@dataclass(frozen=True)
class MarketEstimate:
    status: str
    estimated_value: int | None
    estimated_value_low: int | None
    estimated_value_high: int | None
    transaction_count: int | None
    volatility: float | None
    message: str
    method: str | None = None
    as_of: str | None = None


@dataclass(frozen=True)
class PublicDataResult:
    address: ResolvedAddress | None
    building: OfficialBuilding
    market: MarketEstimate


@dataclass(frozen=True)
class Trade:
    amount: int
    area: float
    legal_dong_name: str
    jibun: str
    building_name: str
    year: int
    month: int


def _secret_value(value: Any) -> str | None:
    if value is None:
        return None
    raw = value.get_secret_value().strip()
    return unquote(raw) if "%" in raw else raw


def _base_address(value: str) -> str:
    return re.sub(r"\s*,?\s*[^,\s]*\d{1,5}\s*호(?:\s.*)?$", "", value).strip()


def _unit_name(value: str) -> str | None:
    match = re.search(r"([가-힣A-Za-z0-9-]*\d{1,5})\s*호\b", value)
    return match.group(1) if match else None


def _normalize_unit(value: str | None) -> str:
    return re.sub(r"[^가-힣a-z0-9]", "", (value or "").lower().replace("호", ""))


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("response", {}).get("body", {}).get("items")
    if not isinstance(items, dict):
        return []
    value = items.get("item", [])
    if isinstance(value, dict):
        return [value]
    return value if isinstance(value, list) else []


def _optional_yes_no(value: Any) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    normalized = str(value).strip().lower()
    if normalized in {"y", "yes", "1", "true", "해당"}:
        return True
    if normalized in {"n", "no", "0", "false", "미해당"}:
        return False
    return None


async def search_resolved_addresses(
    keyword: str,
    *,
    limit: int = 10,
    settings: Settings | None = None,
) -> list[ResolvedAddress]:
    config = settings or get_settings()
    key = _secret_value(config.juso_confirm_key)
    if not key:
        raise PublicAPIError("주소 검색 API 키가 설정되지 않았습니다.")

    params = {
        "confmKey": key,
        "currentPage": 1,
        "countPerPage": max(1, min(limit, 20)),
        "keyword": _base_address(keyword),
        "resultType": "json",
        "hstryYn": "N",
        "firstSort": "road",
    }
    try:
        async with httpx.AsyncClient(timeout=config.public_api_timeout_seconds) as client:
            response = await client.get(JUSO_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise PublicAPIError("주소 검색 기관에 연결하지 못했습니다.") from exc

    common = payload.get("results", {}).get("common", {})
    if str(common.get("errorCode")) != "0":
        raise PublicAPIError(str(common.get("errorMessage") or "주소 검색에 실패했습니다."))

    results: list[ResolvedAddress] = []
    for item in payload.get("results", {}).get("juso", []):
        adm_code = str(item.get("admCd") or "")
        lot_main = str(item.get("lnbrMnnm") or "")
        if len(adm_code) != 10 or not lot_main.isdigit():
            continue
        lot_sub = str(item.get("lnbrSlno") or "0")
        results.append(
            ResolvedAddress(
                road_address=str(item.get("roadAddr") or item.get("roadAddrPart1") or ""),
                jibun_address=str(item.get("jibunAddr") or ""),
                zip_code=str(item.get("zipNo") or ""),
                building_name=str(item.get("bdNm") or "").strip() or None,
                adm_code=adm_code,
                legal_dong_name=str(item.get("emdNm") or "").strip(),
                mountain=str(item.get("mtYn") or "0") == "1",
                lot_main=int(lot_main),
                lot_sub=int(lot_sub) if lot_sub.isdigit() else 0,
            )
        )
    return results


async def search_addresses(keyword: str, *, limit: int = 10) -> list[AddressSuggestion]:
    return [
        AddressSuggestion(
            road_address=item.road_address,
            jibun_address=item.jibun_address,
            zip_code=item.zip_code,
            building_name=item.building_name,
        )
        for item in await search_resolved_addresses(keyword, limit=limit)
    ]


def _building_params(address: ResolvedAddress, key: str) -> dict[str, Any]:
    return {
        "serviceKey": key,
        "sigunguCd": address.sigungu_code,
        "bjdongCd": address.bjdong_code,
        "platGbCd": "1" if address.mountain else "0",
        "bun": f"{address.lot_main:04d}",
        "ji": f"{address.lot_sub:04d}",
        "numOfRows": 1000,
        "pageNo": 1,
        "_type": "json",
    }


async def _get_building_data(
    address: ResolvedAddress,
    input_address: str,
    settings: Settings,
) -> OfficialBuilding:
    key = _secret_value(settings.data_go_kr_service_key)
    if not key:
        return OfficialBuilding(status="unavailable", message="공공데이터포털 키가 설정되지 않았습니다.")

    params = _building_params(address, key)
    try:
        async with httpx.AsyncClient(timeout=settings.public_api_timeout_seconds) as client:
            # Avoid concurrent calls with the same key because the provider can
            # throttle the title and area endpoints independently.
            title_response = await client.get(BUILDING_TITLE_URL, params=params)
            area_response = await client.get(BUILDING_AREA_URL, params=params)
            title_response.raise_for_status()
            area_response.raise_for_status()
            title_payload = title_response.json()
            area_payload = area_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return OfficialBuilding(status="unavailable", message="건축HUB 응답을 확인하지 못했습니다.")

    header = title_payload.get("response", {}).get("header", {})
    if str(header.get("resultCode")) not in {"00", "000"}:
        return OfficialBuilding(status="unavailable", message="건축HUB 활용 권한 또는 응답을 확인해주세요.")
    titles = _items(title_payload)
    if not titles:
        return OfficialBuilding(status="unavailable", message="입력 주소의 공식 건축물 표제부를 찾지 못했습니다.")

    title = titles[0]
    unit = _normalize_unit(_unit_name(input_address))
    exclusive_area = None
    if unit:
        areas = []
        for item in _items(area_payload):
            if _normalize_unit(str(item.get("hoNm") or "")) != unit:
                continue
            if "전유" not in str(item.get("exposPubuseGbCdNm") or ""):
                continue
            try:
                areas.append(float(item.get("area")))
            except (TypeError, ValueError):
                continue
        if areas:
            exclusive_area = sum(areas)

    return OfficialBuilding(
        status="available",
        address=str(title.get("newPlatPlc") or title.get("platPlc") or "").strip() or None,
        main_use=str(title.get("mainPurpsCdNm") or title.get("etcPurps") or "").strip() or None,
        approval_date=str(title.get("useAprDay") or "").strip() or None,
        exclusive_area=exclusive_area,
        # The current Building HUB title response usually omits this field, but
        # some provider versions expose it under one of these names.
        is_illegal_building=_optional_yes_no(
            title.get("violBldYn")
            or title.get("violBldAt")
            or title.get("illegalBldYn")
        ),
        message="건축HUB 공식 표제부를 확인했습니다.",
    )


def _month_keys(count: int, *, today: date | None = None) -> list[str]:
    current = today or date.today()
    year, month = current.year, current.month - 1
    if month == 0:
        year, month = year - 1, 12
    values = []
    for _ in range(count):
        values.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return values


async def _get_trade_month(
    client: httpx.AsyncClient,
    key: str,
    lawd_code: str,
    month: str,
) -> list[Trade]:
    response = await client.get(
        TRADE_URL,
        params={
            "serviceKey": key,
            "LAWD_CD": lawd_code,
            "DEAL_YMD": month,
            "numOfRows": 1000,
            "pageNo": 1,
        },
    )
    response.raise_for_status()
    root = ElementTree.fromstring(response.content)
    code = root.findtext("./header/resultCode")
    if code not in {"00", "000"}:
        raise PublicAPIError(root.findtext("./header/resultMsg") or "실거래가 API 호출에 실패했습니다.")

    trades: list[Trade] = []
    for item in root.findall("./body/items/item"):
        try:
            amount = int((item.findtext("dealAmount") or "").replace(",", "").strip()) * 10_000
            area = float(item.findtext("excluUseAr") or "0")
            year = int(item.findtext("dealYear") or month[:4])
            deal_month = int(item.findtext("dealMonth") or month[4:])
        except ValueError:
            continue
        if amount <= 0 or area <= 0:
            continue
        trades.append(
            Trade(
                amount=amount,
                area=area,
                legal_dong_name=(item.findtext("umdNm") or "").strip(),
                jibun=(item.findtext("jibun") or "").strip(),
                building_name=(item.findtext("mhouseNm") or "").strip(),
                year=year,
                month=deal_month,
            )
        )
    return trades


def _normalized_jibun(value: str) -> str:
    match = re.match(r"\s*(\d+)(?:-(\d+))?", value)
    if not match:
        return value.strip()
    main = int(match.group(1))
    sub = int(match.group(2) or 0)
    return f"{main}-{sub}" if sub else str(main)


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _round_won(value: float) -> int:
    return max(1_000_000, int(round(value / 1_000_000) * 1_000_000))


def estimate_market_value(
    trades: list[Trade],
    address: ResolvedAddress,
    target_area: float | None,
    *,
    as_of: str,
) -> MarketEstimate:
    same_dong = [trade for trade in trades if trade.legal_dong_name == address.legal_dong_name]
    exact = [trade for trade in same_dong if _normalized_jibun(trade.jibun) == address.jibun]

    method: str | None = None
    if target_area:
        exact_similar = [trade for trade in exact if abs(trade.area - target_area) / target_area <= 0.2]
        nearby_similar = [trade for trade in same_dong if abs(trade.area - target_area) / target_area <= 0.15]
        if exact_similar:
            comparables = exact_similar
            method = "같은 지번·유사 전용면적 거래의 ㎡당 중간가격"
        elif len(nearby_similar) >= 3:
            comparables = nearby_similar
            method = "같은 법정동·유사 전용면적 거래의 ㎡당 중간가격"
        else:
            comparables = []
    else:
        comparables = exact
        if exact:
            method = "같은 지번 거래의 중간가격"

    if not comparables:
        return MarketEstimate(
            status="unavailable",
            estimated_value=None,
            estimated_value_low=None,
            estimated_value_high=None,
            transaction_count=0,
            volatility=None,
            message="최근 12개월 내 동일·유사 매물의 비교 거래가 부족해 주택가액을 계산하지 않았습니다.",
            as_of=as_of,
        )

    if target_area:
        unit_prices = [trade.amount / trade.area for trade in comparables]
        estimated_samples = [unit_price * target_area for unit_price in unit_prices]
        samples = unit_prices
    else:
        estimated_samples = [float(trade.amount) for trade in comparables]
        samples = estimated_samples
    estimate = _round_won(statistics.median(estimated_samples))
    estimate_low = _round_won(_percentile(estimated_samples, .25))
    estimate_high = _round_won(_percentile(estimated_samples, .75))
    mean = statistics.fmean(samples)
    volatility = statistics.pstdev(samples) / mean if len(samples) > 1 and mean else 0.0
    return MarketEstimate(
        status="available",
        estimated_value=estimate,
        estimated_value_low=min(estimate_low, estimate),
        estimated_value_high=max(estimate_high, estimate),
        transaction_count=len(comparables),
        volatility=volatility if math.isfinite(volatility) else None,
        message=f"국토교통부 최근 실거래 {len(comparables)}건을 비교했습니다.",
        method=method,
        as_of=as_of,
    )


async def _get_market_data(
    address: ResolvedAddress,
    target_area: float | None,
    settings: Settings,
) -> MarketEstimate:
    key = _secret_value(settings.data_go_kr_service_key)
    if not key:
        return MarketEstimate(
            status="unavailable",
            estimated_value=None,
            estimated_value_low=None,
            estimated_value_high=None,
            transaction_count=None,
            volatility=None,
            message="공공데이터포털 키가 설정되지 않았습니다.",
        )
    months = _month_keys(settings.public_market_months)
    try:
        async with httpx.AsyncClient(timeout=settings.public_api_timeout_seconds) as client:
            batches = await asyncio.gather(
                *(_get_trade_month(client, key, address.sigungu_code, month) for month in months)
            )
    except (httpx.HTTPError, ElementTree.ParseError, PublicAPIError):
        return MarketEstimate(
            status="unavailable",
            estimated_value=None,
            estimated_value_low=None,
            estimated_value_high=None,
            transaction_count=None,
            volatility=None,
            message="국토교통부 실거래가 응답을 확인하지 못했습니다.",
        )
    return estimate_market_value(
        [trade for batch in batches for trade in batch],
        address,
        target_area,
        as_of=months[0],
    )


async def fetch_public_data(address: str) -> PublicDataResult:
    settings = get_settings()
    try:
        matches = await search_resolved_addresses(address, limit=1, settings=settings)
    except PublicAPIError as exc:
        message = str(exc)
        return PublicDataResult(
            address=None,
            building=OfficialBuilding(status="unavailable", message=message),
            market=MarketEstimate(
                status="unavailable",
                estimated_value=None,
                estimated_value_low=None,
                estimated_value_high=None,
                transaction_count=None,
                volatility=None,
                message=message,
            ),
        )
    if not matches:
        message = "입력 주소를 공공 주소정보에서 찾지 못해 공식 데이터 조회를 건너뛰었습니다."
        return PublicDataResult(
            address=None,
            building=OfficialBuilding(status="unavailable", message=message),
            market=MarketEstimate(
                status="unavailable",
                estimated_value=None,
                estimated_value_low=None,
                estimated_value_high=None,
                transaction_count=None,
                volatility=None,
                message=message,
            ),
        )

    resolved = matches[0]
    building = await _get_building_data(resolved, address, settings)
    market = await _get_market_data(resolved, building.exclusive_area, settings)
    return PublicDataResult(address=resolved, building=building, market=market)
