from app.services.cross_checker import _address_matches


def test_registry_document_heading_does_not_cause_address_mismatch():
    assert _address_matches(
        "서울특별시 테스트구 안전로 123, 201호",
        "[집합건물]서울특별시 테스트구 안전로123,201호",
        "서울특별시테스트구안전로123,201호",
        "서울특별시 테스트구안전로123,201호",
    ) is True
