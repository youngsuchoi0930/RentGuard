from app.services.lease_parser import parse_lease_contract
from app.services.pdf_extractor import ExtractedDocument, ExtractedPage


def _ocr_document(text: str) -> ExtractedDocument:
    return ExtractedDocument(
        pages=[ExtractedPage(number=1, text=text, confidence=0.97)],
        method="ocr",
    )


def test_inline_ocr_money_values_beat_unrelated_exact_label_cells():
    document = _ocr_document(
        """주택임대차표준계약서
보증금있는월세
월세
임대인 홍길동과 임차인 이서연은 아래와 같이 임대차계약을 체결한다.
소재지 서울특별시 테스트구 안전로 123, 201호
보증금150,000,000원
계약금15,000,000원
잔금135,000,000원
차임100,000원,매월8일
임대차기간2026.09.08~2028.09.07
보증금
증액 시 확정일자 확인"""
    )

    result = parse_lease_contract(document)

    assert result.document.contract_type == "monthly_with_deposit"
    assert result.deposit.value == 150_000_000
    assert result.contract_payment.value == 15_000_000
    assert result.balance.value == 135_000_000
    assert result.monthly_rent.value == 100_000
    assert result.lease_period.start == "2026-09-08"
    assert result.lease_period.end == "2028-09-07"


def test_intro_parties_are_not_duplicated_by_blank_party_table_labels():
    document = _ocr_document(
        """주택임대차표준계약서
임대인 홍길동과 임차인 이서연은 아래와 같이 임대차계약을 체결한다.
임대인
주민등록번호
임차인
주민등록번호"""
    )

    result = parse_lease_contract(document)

    assert [(party.role, party.name) for party in result.parties] == [
        ("landlord", "홍길동"),
        ("tenant", "이서연"),
    ]
