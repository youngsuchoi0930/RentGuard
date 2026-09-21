"""Evaluate private real-document fixtures without adding them to Git.

Each case lives under ``local-fixtures/case-xxx`` and contains ``expected.json``
plus the PDFs named in this module.  Reports are written below the ignored
``local-fixtures`` directory so extracted personal data cannot be committed by
accident.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.services.building_parser import extract_building_ledger  # noqa: E402
from app.services.cross_checker import _address_key, cross_check_documents  # noqa: E402
from app.services.lease_parser import extract_lease_contract  # noqa: E402
from app.services.registry_parser import extract_registry  # noqa: E402


DEFAULT_CASES_DIR = ROOT / "local-fixtures"
DOCUMENT_FILES = {
    "registry": "registry.pdf",
    "building_ledger": "building-ledger.pdf",
    "lease_contract": "lease-contract.pdf",
}
ADDRESS_FIELDS = {
    "registry.road_address",
    "building_ledger.road_address",
    "lease_contract.address",
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=DEFAULT_CASES_DIR)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Evaluate only this directory name or case_id; repeat to select several cases",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Defaults to <cases-dir>/holdout-evaluation.json",
    )
    parser.add_argument("--no-ocr", action="store_true", help="Reject image-only PDFs")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any labelled field differs or any case errors",
    )
    return parser.parse_args()


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value).strip().lower()


def _semantic_value(path: str, value: Any) -> Any:
    if isinstance(value, str):
        if path in ADDRESS_FIELDS:
            return _address_key(value)
        return _compact(value)
    if isinstance(value, dict):
        return {
            key: _semantic_value(f"{path}.{key}" if path else key, item)
            for key, item in sorted(value.items())
        }
    if isinstance(value, list):
        normalized = [_semantic_value(path, item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
    return value


def _project_item(actual: Any, expected: Any) -> Any:
    """Keep only labelled keys so an intentionally partial annotation is valid."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return {
            key: _project_item(actual.get(key), value)
            for key, value in expected.items()
        }
    return actual


def _collection_counts(path: str, expected: list[Any], actual: list[Any]) -> tuple[int, int, int]:
    if expected and isinstance(expected[0], dict):
        shape = expected[0]
        actual = [_project_item(item, shape) for item in actual]
    expected_values = [
        json.dumps(_semantic_value(path, item), ensure_ascii=False, sort_keys=True)
        for item in expected
    ]
    actual_values = [
        json.dumps(_semantic_value(path, item), ensure_ascii=False, sort_keys=True)
        for item in actual
    ]
    remaining = list(actual_values)
    true_positive = 0
    for item in expected_values:
        if item in remaining:
            true_positive += 1
            remaining.remove(item)
    false_negative = len(expected_values) - true_positive
    false_positive = len(remaining)
    return true_positive, false_positive, false_negative


def _compare_section(
    section: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for field, expected_value in expected.items():
        path = f"{section}.{field}"
        actual_value = actual.get(field)
        exact_match = actual_value == expected_value
        passed = _semantic_value(path, actual_value) == _semantic_value(path, expected_value)
        true_positive = false_positive = false_negative = 0
        if isinstance(expected_value, list):
            actual_list = actual_value if isinstance(actual_value, list) else []
            true_positive, false_positive, false_negative = _collection_counts(
                path,
                expected_value,
                actual_list,
            )
            passed = false_positive == 0 and false_negative == 0
        elif passed:
            true_positive = 1
        elif actual_value is None:
            false_negative = 1
        else:
            false_positive = 1
            false_negative = 1
        comparisons.append({
            "field": path,
            "expected": expected_value,
            "actual": actual_value,
            "exact_match": exact_match,
            "passed": passed,
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
        })
    return comparisons


def _check_result(checks: dict[str, str], check_id: str) -> bool | None:
    status = checks.get(check_id)
    if status == "verified":
        return True
    if status == "mismatch":
        return False
    return None


def _actual_values(registry: Any, ledger: Any, contract: Any, bundle: Any) -> dict[str, Any]:
    active_owners = [item.owner_name for item in registry.ownership if item.status == "active"]
    active_mortgages = [
        {
            "holder": item.holder,
            "debtor": item.debtor,
            "maximum_claim_amount": item.maximum_claim_amount,
        }
        for item in registry.encumbrances
        if item.status == "active" and item.right_type == "mortgage"
    ]
    active_right_types = sorted({
        item.right_type for item in registry.encumbrances if item.status == "active"
    })
    checks = {item.id: item.status for item in bundle.cross_checks}
    actual: dict[str, Any] = {
        "registry": {
            "owners": active_owners,
            "road_address": registry.property.road_address,
            "mortgages": active_mortgages,
            "active_right_types": active_right_types,
        },
        "building_ledger": {
            "road_address": ledger.property.road_address,
            "building_name": ledger.property.building_name,
            "main_use": ledger.property.main_use,
            "is_illegal_building": ledger.property.is_illegal_building,
        },
        "cross_checks": {
            "property_address_match": _check_result(checks, "property-address"),
            "registry_owner_found": _check_result(checks, "registry-owner"),
            "illegal_building_clear": _check_result(checks, "illegal-building"),
            "owner_landlord_match": _check_result(checks, "owner-landlord"),
            "deposit_match": _check_result(checks, "deposit"),
            "monthly_rent_match": _check_result(checks, "monthly-rent"),
        },
    }
    if contract is not None:
        actual["lease_contract"] = {
            "landlord": next((item.name for item in contract.parties if item.role == "landlord"), None),
            "tenant": next((item.name for item in contract.parties if item.role == "tenant"), None),
            "address": contract.property.address,
            "deposit": contract.deposit.value,
            "monthly_rent": contract.monthly_rent.value,
            "lease_start": contract.lease_period.start,
            "lease_end": contract.lease_period.end,
        }
    return actual


def _review_codes(extraction: Any | None) -> list[str]:
    return [item.code for item in extraction.needs_review] if extraction is not None else []


def _case_directories(cases_dir: Path, selected: set[str]) -> list[Path]:
    directories = sorted(
        path for path in cases_dir.iterdir()
        if path.is_dir() and (path / "expected.json").is_file()
    ) if cases_dir.is_dir() else []
    if not selected:
        return directories
    chosen = []
    for path in directories:
        metadata = json.loads((path / "expected.json").read_text(encoding="utf-8"))
        if path.name in selected or metadata.get("case_id") in selected:
            chosen.append(path)
    return chosen


def _evaluate_case(case_dir: Path, *, allow_ocr: bool) -> dict[str, Any]:
    metadata = json.loads((case_dir / "expected.json").read_text(encoding="utf-8"))
    expected = metadata["expected"]
    inputs = metadata["input"]
    registry_path = case_dir / DOCUMENT_FILES["registry"]
    ledger_path = case_dir / DOCUMENT_FILES["building_ledger"]
    contract_path = case_dir / DOCUMENT_FILES["lease_contract"]
    required = [registry_path, ledger_path]
    if "lease_contract" in expected:
        required.append(contract_path)
    missing = [path.name for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing files in {case_dir.name}: {', '.join(missing)}")

    registry = extract_registry(registry_path.read_bytes(), allow_ocr=allow_ocr)
    ledger = extract_building_ledger(ledger_path.read_bytes(), allow_ocr=allow_ocr)
    contract = (
        extract_lease_contract(contract_path.read_bytes(), allow_ocr=allow_ocr)
        if contract_path.is_file() and "lease_contract" in expected
        else None
    )
    bundle = cross_check_documents(
        registry,
        ledger,
        contract,
        input_address=inputs["address"],
        input_deposit=inputs["deposit"],
        input_monthly_rent=inputs["monthly_rent"],
    )
    actual = _actual_values(registry, ledger, contract, bundle)
    comparisons: list[dict[str, Any]] = []
    for section, expected_section in expected.items():
        comparisons.extend(_compare_section(section, expected_section, actual.get(section, {})))
    return {
        "case_id": metadata.get("case_id", case_dir.name),
        "directory": case_dir.name,
        "source_type": metadata.get("source_type", "private_real_document"),
        "passed": all(item["passed"] for item in comparisons),
        "field_count": len(comparisons),
        "matched_fields": sum(item["passed"] for item in comparisons),
        "extraction_method": {
            "registry": registry.extraction_method,
            "building_ledger": ledger.extraction_method,
            "lease_contract": contract.extraction_method if contract else None,
        },
        "review_codes": {
            "registry": _review_codes(registry),
            "building_ledger": _review_codes(ledger),
            "lease_contract": _review_codes(contract),
        },
        "comparisons": comparisons,
    }


def _summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = [item for case in cases for item in case.get("comparisons", [])]
    true_positive = sum(item["true_positive"] for item in comparisons)
    false_positive = sum(item["false_positive"] for item in comparisons)
    false_negative = sum(item["false_negative"] for item in comparisons)
    fields = len(comparisons)
    matched = sum(item["passed"] for item in comparisons)
    exact_matched = sum(item["exact_match"] for item in comparisons)
    precision_denominator = true_positive + false_positive
    recall_denominator = true_positive + false_negative
    return {
        "case_count": len(cases),
        "passed_cases": sum(case.get("passed", False) for case in cases),
        "failed_cases": sum(not case.get("passed", False) for case in cases),
        "matched_fields": matched,
        "exact_matched_fields": exact_matched,
        "total_fields": fields,
        "field_accuracy": matched / fields if fields else 1.0,
        "exact_field_accuracy": exact_matched / fields if fields else 1.0,
        "true_positive_values": true_positive,
        "false_positive_values": false_positive,
        "false_negative_values": false_negative,
        "value_precision": (
            true_positive / precision_denominator if precision_denominator else 1.0
        ),
        "value_recall": true_positive / recall_denominator if recall_denominator else 1.0,
    }


def evaluate(cases_dir: Path, *, selected: set[str], allow_ocr: bool) -> dict[str, Any]:
    directories = _case_directories(cases_dir, selected)
    if not directories:
        requested = ", ".join(sorted(selected)) if selected else str(cases_dir)
        raise FileNotFoundError(f"No private holdout cases found for: {requested}")
    cases: list[dict[str, Any]] = []
    for case_dir in directories:
        try:
            cases.append(_evaluate_case(case_dir, allow_ocr=allow_ocr))
        except Exception as error:  # Keep the remaining private cases evaluable.
            cases.append({
                "case_id": case_dir.name,
                "directory": case_dir.name,
                "passed": False,
                "error": f"{type(error).__name__}: {error}",
                "comparisons": [],
            })
    summary = _summarize(cases)
    summary["errored_cases"] = sum("error" in case for case in cases)
    return {
        "evaluation_version": "private-holdout-1.0",
        "source_kind": "private_real_document",
        **summary,
        "cases": cases,
    }


def main() -> None:
    args = _args()
    cases_dir = args.cases_dir.resolve()
    output = args.output.resolve() if args.output else cases_dir / "holdout-evaluation.json"
    result = evaluate(
        cases_dir,
        selected=set(args.case_ids or []),
        allow_ocr=not args.no_ocr,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {key: value for key, value in result.items() if key != "cases"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Private report: {output}")
    if args.strict and (result["failed_cases"] or result["errored_cases"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
