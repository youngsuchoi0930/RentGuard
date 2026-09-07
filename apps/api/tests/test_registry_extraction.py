import json
import os
from pathlib import Path

import pytest

from app.services.pdf_extractor import OCRUnavailableError
from app.services.registry_evaluator import evaluate_registry
from app.services.registry_parser import extract_registry


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
