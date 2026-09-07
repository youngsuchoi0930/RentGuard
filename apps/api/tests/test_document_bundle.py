import json
from pathlib import Path

from app.services.building_parser import extract_building_ledger
from app.services.cross_checker import cross_check_documents
from app.services.lease_parser import extract_lease_contract
from app.services.registry_parser import extract_registry


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "output" / "pdf" / "rentguard-fixtures"
GROUND_TRUTH = json.loads((FIXTURES / "ground_truth.json").read_text(encoding="utf-8"))


def test_lease_contract_extracts_expected_fields():
    result = extract_lease_contract((FIXTURES / "lease_contract_risky.pdf").read_bytes(), allow_ocr=False)
    expected = GROUND_TRUTH["expected"]["lease_contract"]

    assert result.extraction_method == "pdf_text"
    assert result.document.contract_type == "monthly_with_deposit"
    assert next(p.name for p in result.parties if p.role == "landlord") == expected["landlord"]
    assert next(p.name for p in result.parties if p.role == "tenant") == expected["tenant"]
    assert result.deposit.value == expected["deposit"]
    assert result.monthly_rent.value == expected["monthly_rent"]
    assert result.lease_period.start == expected["lease_start"]
    assert result.lease_period.end == expected["lease_end"]
    assert len(result.special_terms) == 3
    assert result.needs_review == []


def test_building_ledger_extracts_expected_fields():
    result = extract_building_ledger((FIXTURES / "building_ledger_risky.pdf").read_bytes(), allow_ocr=False)
    expected = GROUND_TRUTH["expected"]["building_ledger"]

    assert result.extraction_method == "pdf_text"
    assert result.document.ledger_type == "general"
    assert result.property.main_use == expected["building_use"]
    assert result.property.is_illegal_building is expected["is_illegal_building"]
    assert result.property.approval_date == expected["approval_date"]
    assert result.property.households == expected["households"]
    assert result.needs_review == []


def test_three_documents_cross_check_against_user_input():
    registry = extract_registry((FIXTURES / "registry_risky_digital.pdf").read_bytes(), allow_ocr=False)
    ledger = extract_building_ledger((FIXTURES / "building_ledger_risky.pdf").read_bytes(), allow_ocr=False)
    contract = extract_lease_contract((FIXTURES / "lease_contract_risky.pdf").read_bytes(), allow_ocr=False)
    user_input = GROUND_TRUTH["input"]

    result = cross_check_documents(
        registry,
        ledger,
        contract,
        input_address=user_input["address"],
        input_deposit=user_input["deposit"],
        input_monthly_rent=user_input["monthly_rent"],
    )

    checks = {check.id: check for check in result.cross_checks}
    assert checks["owner-landlord"].status == "verified"
    assert checks["property-address"].status == "verified"
    assert checks["deposit"].status == "verified"
    assert checks["monthly-rent"].status == "verified"
    assert checks["illegal-building"].status == "verified"


def test_cross_check_reports_mismatch_instead_of_guessing():
    registry = extract_registry((FIXTURES / "registry_risky_digital.pdf").read_bytes(), allow_ocr=False)
    ledger = extract_building_ledger((FIXTURES / "building_ledger_risky.pdf").read_bytes(), allow_ocr=False)
    contract = extract_lease_contract((FIXTURES / "lease_contract_risky.pdf").read_bytes(), allow_ocr=False)

    result = cross_check_documents(
        registry,
        ledger,
        contract,
        input_address="부산광역시 해운대구 테스트로 999",
        input_deposit=99_000_000,
        input_monthly_rent=0,
    )

    checks = {check.id: check for check in result.cross_checks}
    assert checks["property-address"].status == "mismatch"
    assert checks["deposit"].status == "mismatch"
    assert checks["monthly-rent"].status == "mismatch"


def test_wrong_upload_slot_is_flagged_as_blocking_review():
    contract_bytes = (FIXTURES / "lease_contract_risky.pdf").read_bytes()
    ledger_bytes = (FIXTURES / "building_ledger_risky.pdf").read_bytes()

    registry_result = extract_registry(contract_bytes, allow_ocr=False)
    contract_result = extract_lease_contract(ledger_bytes, allow_ocr=False)
    ledger_result = extract_building_ledger(contract_bytes, allow_ocr=False)

    assert any(item.code == "DOCUMENT_TYPE_MISMATCH" and item.severity == "blocking" for item in registry_result.needs_review)
    assert any(item.code == "DOCUMENT_TYPE_MISMATCH" and item.severity == "blocking" for item in contract_result.needs_review)
    assert any(item.code == "DOCUMENT_TYPE_MISMATCH" and item.severity == "blocking" for item in ledger_result.needs_review)
