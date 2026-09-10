import json
import os
from pathlib import Path

import pytest

from app.services.pdf_extractor import OCRUnavailableError
from app.services.pdf_extractor import ExtractedDocument, ExtractedPage
from app.services.registry_evaluator import evaluate_registry
from app.services.registry_parser import extract_registry, parse_registry


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "output" / "pdf" / "rentguard-fixtures"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))


def test_digital_registry_extracts_normalized_arrays_with_provenance():
    result = extract_registry((FIXTURES / "registry_risky_digital.pdf").read_bytes(), allow_ocr=False)

    assert result.extraction_method == "pdf_text"
    assert result.document.certificate_type == "full_with_cancelled"
    assert result.document.property_type == "condominium"
    assert result.property.road_address == "서울특별시 강서구 화곡로 123, 301호"
    assert result.ownership[0].owner_name == "김민준"
    assert result.ownership[0].evidence.page == 1
    assert result.encumbrances[0].right_type == "mortgage"
    assert result.encumbrances[0].maximum_claim_amount == 110_000_000
    assert result.encumbrances[0].holder == "테스트은행"
    assert result.needs_review == []


def test_digital_registry_matches_ground_truth():
    result = extract_registry((FIXTURES / "registry_risky_digital.pdf").read_bytes(), allow_ocr=False)
    evaluation = evaluate_registry(result, GROUND_TRUTH["expected"]["registry"])

    assert evaluation.passed is True
    assert evaluation.matched == evaluation.total == 5
    assert evaluation.accuracy == 1.0


def test_title_address_wins_over_owner_and_debtor_addresses_on_later_pages():
    document = ExtractedDocument(
        method="pdf_text",
        pages=[
            ExtractedPage(
                number=1,
                confidence=1.0,
                text="""
                등기사항전부증명서 현재 유효사항 - 집합건물 -
                [집합건물] 서울특별시 강서구 안전동 870-31외 3필지 제2층 제201호
                서울특별시 강서구 안전동 철근콘크리트조 도로명주소
                [도로명주소] (19
                안심로35길 26 지1층 358.93㎡
                """,
            ),
            ExtractedPage(
                number=2,
                confidence=1.0,
                text="""
                권리자 및 기타사항
                【 갑 구 】 (소유권에 관한 사항)
                10 소유권이전 공유자
                테스트이전 900101-*******
                테스트현재 900202-*******
                11 10번테스트이전지분전부 이전 공유자
                테스트현재 900202-*******
                【 을 구 】 (소유권 이외의 권리에 관한 사항)
                채무자 테스트현재
                서울특별시 강서구 다른로29길
                36, 402호(안전동)
                채권최고액 금31,000,000원
                """,
            ),
        ],
    )

    result = parse_registry(document)

    assert result.property.road_address == "서울특별시 강서구 안심로35길 26"
    assert result.property.lot_address.startswith("[집합건물] 서울특별시 강서구 안전동 870-31")
    assert result.property.unit == "201호"
    assert "다른로29길" not in result.property.road_address
    assert result.evidence["road_address"].page == 1
    assert [owner.owner_name for owner in result.ownership] == ["테스트현재"]


def test_registry_rights_extract_active_and_cancelled_rows_with_order():
    document = ExtractedDocument(
        method="pdf_text",
        pages=[
            ExtractedPage(
                number=1,
                confidence=1.0,
                text="""
                등기사항전부증명서 말소사항포함 - 집합건물 -
                [집합건물] 서울특별시 강서구 안전동 100-1 제2층 제201호
                도로명주소 서울특별시 강서구 안심로35길 26
                【 갑 구 】 소유권에 관한 사항
                1
                2020년 1월 2일
                소유권보존 소유자 테스트소유
                2
                2021년 2월 3일
                가압류
                3
                2022년 3월 4일
                압류
                4
                2023년 4월 5일
                신탁등기
                5
                2024년 5월 6일
                임의경매개시결정
                6
                2025년 6월 7일
                2번 가압류 등기말소
                """,
            ),
            ExtractedPage(
                number=2,
                confidence=1.0,
                text="""
                【 을 구 】 소유권 이외의 권리에 관한 사항
                1
                2018년 1월 2일
                전세권설정
                2
                2019년 2월 3일
                주택임차권등기
                3
                2020년 3월 4일
                근저당권설정
                채권최고액 금90,000,000원
                근저당권자 테스트은행
                4
                2021년 4월 5일
                3번 근저당권설정등기말소
                """,
            ),
        ],
    )

    result = parse_registry(document)
    rights = {(entry.right_type, entry.rank): entry for entry in result.encumbrances}

    assert rights[("provisional_seizure", "2")].status == "cancelled"
    assert rights[("seizure", "3")].status == "active"
    assert rights[("trust", "4")].registered_at == "2023-04-05"
    assert rights[("auction", "5")].status == "active"
    assert rights[("leasehold", "1")].status == "active"
    assert rights[("tenant_registration", "2")].status == "active"
    assert rights[("mortgage", "3")].status == "cancelled"
    assert rights[("mortgage", "3")].maximum_claim_amount == 90_000_000


def test_image_only_pdf_requires_ocr_when_disabled():
    with pytest.raises(OCRUnavailableError):
        extract_registry((FIXTURES / "registry_risky_scan_noisy.pdf").read_bytes(), allow_ocr=False)


@pytest.mark.ocr
@pytest.mark.skipif(os.getenv("RUN_OCR_TESTS") != "1", reason="set RUN_OCR_TESTS=1 to run the OCR model")
def test_scanned_registry_matches_ground_truth():
    result = extract_registry((FIXTURES / "registry_risky_scan_noisy.pdf").read_bytes())
    evaluation = evaluate_registry(result, GROUND_TRUTH["expected"]["registry"])

    assert result.extraction_method == "ocr"
    assert result.property.road_address == "서울특별시 강서구화곡로123, 301호"
    assert result.encumbrances[0].maximum_claim_amount == 110_000_000
    assert result.needs_review == []
    assert evaluation.passed is True
