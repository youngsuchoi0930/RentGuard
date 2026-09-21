"""Run PaddleOCR on the image-only corpus and compare critical fields."""

from __future__ import annotations

import argparse
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.building_parser import extract_building_ledger  # noqa: E402
from app.services.cross_checker import _address_key, cross_check_documents  # noqa: E402
from app.services.lease_parser import extract_lease_contract  # noqa: E402
from app.services.registry_parser import extract_registry  # noqa: E402


DEFAULT_DIR = ROOT / "output" / "pdf" / "rentguard-ocr-corpus"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_DIR / "rentguard-ocr-corpus-10.pdf")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_DIR / "manifest.json")
    parser.add_argument("--output", type=Path, default=DEFAULT_DIR / "evaluation.json")
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.90,
        help="Exit non-zero when field accuracy falls below this value",
    )
    return parser.parse_args()


def _single_page(reader: PdfReader, page_number: int) -> bytes:
    writer = PdfWriter()
    writer.add_page(reader.pages[page_number - 1])
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


def _compare(prefix: str, expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for field, expected_value in expected.items():
        actual_value = actual.get(field)
        if isinstance(expected_value, list) and isinstance(actual_value, list):
            expected_value = sorted(expected_value)
            actual_value = sorted(actual_value)
        exact_match = actual_value == expected_value
        semantic_match = exact_match
        match_mode = "exact"
        if field in {"road_address", "address"} and isinstance(expected_value, str) and isinstance(actual_value, str):
            match_mode = "address_normalized"
            semantic_match = _address_key(expected_value) == _address_key(actual_value)
        rows.append({
            "field": f"{prefix}.{field}",
            "expected": expected_value,
            "actual": actual_value,
            "match_mode": match_mode,
            "exact_match": exact_match,
            "passed": semantic_match,
        })
    return rows


def evaluate(pdf_path: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    reader = PdfReader(str(pdf_path))
    if len(reader.pages) != manifest["page_count"]:
        raise ValueError(
            f"Page count mismatch: PDF={len(reader.pages)} manifest={manifest['page_count']}"
        )

    cases = []
    total = 0
    matched = 0
    exact_matched = 0
    for case in manifest["cases"]:
        pages = case["pages"]
        registry = extract_registry(_single_page(reader, pages["registry"]))
        ledger = extract_building_ledger(_single_page(reader, pages["building_ledger"]))
        contract = extract_lease_contract(_single_page(reader, pages["lease_contract"]))
        bundle = cross_check_documents(
            registry,
            ledger,
            contract,
            input_address=case["input"]["address"],
            input_deposit=case["input"]["deposit"],
            input_monthly_rent=case["input"]["monthly_rent"],
        )

        active_rights = [entry for entry in registry.encumbrances if entry.status == "active"]
        actual = {
            "registry": {
                "owner": registry.ownership[0].owner_name if registry.ownership else None,
                "mortgage_amount": sum(
                    entry.maximum_claim_amount or 0
                    for entry in active_rights
                    if entry.right_type == "mortgage"
                ),
                "active_right_types": sorted({entry.right_type for entry in active_rights}),
            },
            "building_ledger": {
                "road_address": ledger.property.road_address,
                "main_use": ledger.property.main_use,
                "is_illegal_building": ledger.property.is_illegal_building,
            },
            "lease_contract": {
                "landlord": next((item.name for item in contract.parties if item.role == "landlord"), None),
                "tenant": next((item.name for item in contract.parties if item.role == "tenant"), None),
                "address": contract.property.address,
                "deposit": contract.deposit.value,
                "monthly_rent": contract.monthly_rent.value,
            },
            "cross_checks": {item.id: item.status for item in bundle.cross_checks},
        }
        expected = case["expected"]
        comparisons = []
        for section in ("registry", "building_ledger", "lease_contract", "cross_checks"):
            comparisons.extend(_compare(section, expected[section], actual[section]))
        case_matched = sum(item["passed"] for item in comparisons)
        case_exact_matched = sum(item["exact_match"] for item in comparisons)
        case_total = len(comparisons)
        total += case_total
        matched += case_matched
        exact_matched += case_exact_matched
        cases.append({
            "case_id": case["case_id"],
            "profile": case["profile"],
            "ocr_profile": case["ocr_profile"],
            "passed": case_matched == case_total,
            "matched": case_matched,
            "exact_matched": case_exact_matched,
            "total": case_total,
            "accuracy": case_matched / case_total,
            "exact_accuracy": case_exact_matched / case_total,
            "extraction_method": {
                "registry": registry.extraction_method,
                "building_ledger": ledger.extraction_method,
                "lease_contract": contract.extraction_method,
            },
            "review_codes": {
                "registry": [item.code for item in registry.needs_review],
                "building_ledger": [item.code for item in ledger.needs_review],
                "lease_contract": [item.code for item in contract.needs_review],
            },
            "comparisons": comparisons,
        })

    return {
        "corpus_version": manifest["corpus_version"],
        "source_kind": "synthetic_ocr",
        "case_count": len(cases),
        "passed_cases": sum(case["passed"] for case in cases),
        "failed_cases": sum(not case["passed"] for case in cases),
        "matched_fields": matched,
        "exact_matched_fields": exact_matched,
        "total_fields": total,
        "accuracy": matched / total if total else 1.0,
        "exact_accuracy": exact_matched / total if total else 1.0,
        "cases": cases,
    }


def main() -> None:
    args = _args()
    result = evaluate(args.pdf, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "cases"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if result["accuracy"] < args.min_accuracy:
        raise SystemExit(
            f"OCR field accuracy {result['accuracy']:.3f} is below {args.min_accuracy:.3f}"
        )


if __name__ == "__main__":
    main()
