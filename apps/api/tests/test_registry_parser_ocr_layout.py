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
