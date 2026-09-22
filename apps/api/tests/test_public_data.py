import asyncio
from datetime import date
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from app.services import public_data
from app.services.public_data import (
    MarketEstimate,
    OfficialBuilding,
    ResolvedAddress,
    Trade,
    _base_address,
    _building_response_payload,
    _get_building_data,
    _month_keys,
    _optional_yes_no,
    _provider_error_message,
    estimate_market_value,
    fetch_public_data,
)


def _address() -> ResolvedAddress:
    return ResolvedAddress(
        road_address="서울특별시 강남구 테스트로 10",
        jibun_address="서울특별시 강남구 역삼동 123-4",
        zip_code="00000",
        building_name="테스트빌라",
        adm_code="1168010100",
        legal_dong_name="역삼동",
        mountain=False,
        lot_main=123,
        lot_sub=4,
    )


def test_base_address_removes_unit_number_for_provider_search():
    assert _base_address("서울특별시 강남구 테스트로 10, 201호") == "서울특별시 강남구 테스트로 10"


def test_month_keys_use_completed_months():
    assert _month_keys(3, today=date(2026, 1, 3)) == ["202512", "202511", "202510"]


def test_optional_yes_no_parses_provider_flags():
    assert _optional_yes_no("Y") is True
    assert _optional_yes_no("N") is False
    assert _optional_yes_no(None) is None


def test_building_provider_errors_are_explained_by_category():
    assert "활용 권한" in _provider_error_message(
        {"resultCode": "20", "resultMsg": "SERVICE_ACCESS_DENIED_ERROR"},
        "건축HUB 표제부",
    )
    assert "호출 한도" in _provider_error_message(
        {"resultCode": "22", "resultMsg": "LIMITED_NUMBER"},
        "건축HUB 표제부",
    )
    assert _provider_error_message(
        {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
        "건축HUB 표제부",
    ) is None


def test_building_provider_xml_error_is_explained_by_category():
    response = httpx.Response(
        200,
        content=(
            b"<OpenAPI_ServiceResponse><cmmMsgHeader>"
            b"<returnReasonCode>22</returnReasonCode>"
            b"<returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg>"
            b"<resultCode>22</resultCode>"
            b"<resultMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</resultMsg>"
            b"</cmmMsgHeader></OpenAPI_ServiceResponse>"
        ),
    )

    with pytest.raises(public_data.PublicAPIError, match="호출 한도"):
        _building_response_payload(response, "건축HUB 표제부")


def test_building_title_remains_available_when_optional_area_request_fails(monkeypatch):
    calls = []

    async def fake_request(_client, url, params, _resource):
        calls.append((url, params))
        if url == public_data.BUILDING_AREA_URL:
            raise public_data.PublicAPIError("건축HUB 전유면적 응답 시간이 초과되었습니다.")
        return {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": {"item": [
                    {"dongNm": "203동", "bldNm": "테스트단지", "mainPurpsCdNm": "상가", "useAprDay": "20200101"},
                    {"dongNm": "204동", "bldNm": "테스트단지", "mainPurpsCdNm": "공동주택", "useAprDay": "20220831", "newPlatPlc": "서울특별시 강남구 테스트로 10"},
                ]}},
            }
        }

    monkeypatch.setattr(public_data, "_request_building_json", fake_request)
    settings = SimpleNamespace(
        data_go_kr_service_key=SecretStr("test-key"),
        public_api_timeout_seconds=1.0,
    )
    result = asyncio.run(_get_building_data(
        _address(),
        "서울특별시 강남구 테스트로 10",
        settings,
        document_building_name="테스트단지 204동",
        document_unit="203호",
        document_area=79.97,
    ))

    assert result.status == "available"
    assert result.main_use == "공동주택"
    assert result.approval_date == "20220831"
    assert result.exclusive_area is None
    assert result.message and "표제부는 확인" in result.message
    area_params = next(params for url, params in calls if url == public_data.BUILDING_AREA_URL)
    assert area_params["dongNm"] == "204동"
    assert area_params["hoNm"] == "203"


def test_building_area_uses_document_dong_and_unit(monkeypatch):
    async def fake_request(_client, url, _params, _resource):
        if url == public_data.BUILDING_TITLE_URL:
            return {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"items": {"item": [
                        {"dongNm": "204동", "bldNm": "테스트단지", "mainPurpsCdNm": "공동주택"},
                    ]}},
                }
            }
        return {
            "response": {
                "header": {"resultCode": "00"},
                "body": {"items": {"item": [
                    {"dongNm": "204동", "hoNm": "203", "exposPubuseGbCdNm": "전유", "area": 79.97},
                    {"dongNm": "204동", "hoNm": "203", "exposPubuseGbCdNm": "공용", "area": 12.5},
                ]}},
            }
        }

    monkeypatch.setattr(public_data, "_request_building_json", fake_request)
    settings = SimpleNamespace(
        data_go_kr_service_key=SecretStr("test-key"),
        public_api_timeout_seconds=1.0,
    )
    result = asyncio.run(_get_building_data(
        _address(),
        "서울특별시 강남구 테스트로 10",
        settings,
        document_building_name="테스트단지 204동",
        document_unit="203호",
    ))

    assert result.status == "available"
    assert result.exclusive_area == 79.97


def test_market_estimate_prefers_exact_lot_and_similar_area():
    trades = [
        Trade(200_000_000, 50.0, "역삼동", "123-4", "테스트빌라", 2026, 7),
        Trade(220_000_000, 50.0, "역삼동", "123-4", "테스트빌라", 2026, 6),
        Trade(900_000_000, 100.0, "역삼동", "123-4", "테스트빌라", 2026, 5),
        Trade(150_000_000, 50.0, "역삼동", "999-1", "다른빌라", 2026, 7),
    ]

    result = estimate_market_value(trades, _address(), 50.0, as_of="202607")

    assert result.status == "available"
    assert result.estimated_value == 210_000_000
    assert result.estimated_value_low == 205_000_000
    assert result.estimated_value_high == 215_000_000
    assert result.transaction_count == 2
    assert result.method and "같은 지번" in result.method


def test_market_estimate_refuses_thin_neighborhood_data():
    trades = [Trade(200_000_000, 50.0, "역삼동", "999-1", "다른빌라", 2026, 7)]

    result = estimate_market_value(trades, _address(), 50.0, as_of="202607")

    assert result.status == "unavailable"
    assert result.estimated_value is None
    assert result.estimated_value_low is None
    assert result.estimated_value_high is None


def test_public_data_uses_document_area_when_address_has_no_unit(monkeypatch):
    captured_area = None

    async def fake_search(*_args, **_kwargs):
        return [_address()]

    async def fake_building(*_args, **_kwargs):
        return OfficialBuilding(status="available", exclusive_area=None)

    async def fake_market(_address_value, target_area, _settings):
        nonlocal captured_area
        captured_area = target_area
        return MarketEstimate(
            status="available",
            estimated_value=300_000_000,
            estimated_value_low=280_000_000,
            estimated_value_high=320_000_000,
            transaction_count=10,
            volatility=.05,
            message="테스트",
        )

    monkeypatch.setattr(public_data, "search_resolved_addresses", fake_search)
    monkeypatch.setattr(public_data, "_get_building_data", fake_building)
    monkeypatch.setattr(public_data, "_get_market_data", fake_market)

    result = asyncio.run(fetch_public_data("서울특별시 강남구 테스트로 10", document_area=84.59))

    assert result.market.status == "available"
    assert captured_area == 84.59
