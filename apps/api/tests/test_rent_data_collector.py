from datetime import date

from app.services.rent_data_collector import parse_rent_payload, recent_complete_months


PAYLOAD = b"""<?xml version="1.0" encoding="UTF-8"?>
<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body><items><item>
    <buildYear>2018</buildYear><contractType>\xec\x8b\xa0\xea\xb7\x9c</contractType>
    <dealDay>10</dealDay><dealMonth>1</dealMonth><dealYear>2026</dealYear>
    <deposit>30,000</deposit><excluUseAr>50.0</excluUseAr><floor>3</floor>
    <houseType>\xeb\x8b\xa4\xec\x84\xb8\xeb\x8c\x80</houseType><jibun>123-4</jibun><mhouseNm>\xed\x85\x8c\xec\x8a\xa4\xed\x8a\xb8\xeb\xb9\x8c\xeb\x9d\xbc</mhouseNm>
    <monthlyRent>50</monthlyRent><preDeposit></preDeposit><preMonthlyRent></preMonthlyRent>
    <sggCd>11500</sggCd><umdNm>\xed\x99\x94\xea\xb3\xa1\xeb\x8f\x99</umdNm><useRRRight></useRRRight>
  </item></items><numOfRows>1000</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount></body>
</response>"""


def test_recent_complete_months_excludes_partial_current_month():
    assert recent_complete_months(3, today=date(2026, 9, 10)) == ["202606", "202607", "202608"]


def test_public_rent_parser_sanitizes_location_and_converts_units():
    rows, total = parse_rent_payload(PAYLOAD, district_code="11500", district_name="강서구")

    assert total == 1
    assert len(rows) == 1
    row = rows[0]
    assert row.features.deposit_million_won == 300
    assert row.features.monthly_rent_million_won == .5
    assert row.features.deposit_per_m2_million_won == 6
    assert row.features.building_age_years == 8
    assert row.features.contract_type == "new"
    serialized = row.model_dump_json()
    assert "123-4" not in serialized
    assert "\ud14c\uc2a4\ud2b8\ube4c\ub77c" not in serialized
