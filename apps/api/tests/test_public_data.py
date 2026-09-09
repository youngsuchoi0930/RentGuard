from datetime import date

from app.services.public_data import (
    ResolvedAddress,
    Trade,
    _base_address,
    _month_keys,
    _optional_yes_no,
    estimate_market_value,
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
