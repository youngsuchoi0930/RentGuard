from app.services.pdf_extractor import ExtractedDocument, ExtractedPage
from app.services.registry_parser import parse_registry


def test_share_label_is_not_reported_as_an_owner_name():
    document = ExtractedDocument(
        pages=[
            ExtractedPage(
                number=1,
                text="""등기사항전부증명서 현재 유효사항
[집합건물] 서울특별시 테스트구 안전로 123, 201호
공유자 지분 2분의 1
소유자 홍길동""",
                confidence=0.97,
            )
        ],
        method="ocr",
    )

    result = parse_registry(document)

    assert [owner.owner_name for owner in result.ownership] == ["홍길동"]


def test_inline_mortgage_row_keeps_its_own_rank_and_receipt_date():
    document = ExtractedDocument(
        pages=[
            ExtractedPage(
                number=1,
                text="""등기사항전부증명서 현재 유효사항 - 집합건물 -
[집합건물] 서울특별시 테스트구 안전동 100-1 제2층 제201호
도로명주소 서울특별시 테스트구 안전로 10
【 갑 구 】 (소유권에 관한 사항)
11 소유권이전 2023년5월17일 2023년5월15일 공유자
현재소유자 930608-*******
【 을 구 】 (소유권 이외의 권리에 관한 사항)
순위번호 등기목적 접수 등기원인 권리자 및 기타사항
7 근저당권설정 2022년7월22일 2022년5월30일 채권최고액 금231,000,000원
제152499호 설정계약 채무자 현재소유자""",
                confidence=1.0,
            ),
            ExtractedPage(
                number=2,
                text="""순위번호 등기목적 접수 등기원인 권리자 및 기타사항
근저당권자 테스트은행 110111-*******""",
                confidence=1.0,
            ),
        ],
        method="pdf_text",
    )

    result = parse_registry(document)

    assert len(result.encumbrances) == 1
    mortgage = result.encumbrances[0]
    assert mortgage.rank == "7"
    assert mortgage.registered_at == "2022-07-22"
    assert mortgage.maximum_claim_amount == 231_000_000


def test_inline_mortgage_row_accepts_receipt_date_before_purpose():
    document = ExtractedDocument(
        pages=[
            ExtractedPage(
                number=1,
                text="""등기사항전부증명서 현재 유효사항 - 집합건물 -
[집합건물] 서울특별시 테스트구 안전동 100-1 제201호
도로명주소 서울특별시 테스트구 안전로 10
소유자 현재소유자
【 을 구 】 (소유권 이외의 권리에 관한 사항)
7 2022년7월22일 근저당권설정 채권최고액 금231,000,000원""",
                confidence=1.0,
            )
        ],
        method="pdf_text",
    )

    mortgage = parse_registry(document).encumbrances[0]

    assert mortgage.rank == "7"
    assert mortgage.registered_at == "2022-07-22"
