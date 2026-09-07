from __future__ import annotations

from ..registry_schemas import FieldComparison, RegistryEvaluation, RegistryExtraction


def evaluate_registry(result: RegistryExtraction, expected: dict) -> RegistryEvaluation:
    active_owners = [entry.owner_name for entry in result.ownership if entry.status == "active"]
    active_rights = [entry for entry in result.encumbrances if entry.status == "active"]
    mortgage_amounts = [
        entry.maximum_claim_amount for entry in active_rights
        if entry.right_type == "mortgage" and entry.maximum_claim_amount is not None
    ]
    actual = {
        "owner": active_owners[0] if active_owners else None,
        "mortgage_amount": sum(mortgage_amounts),
        "seizure": any(entry.right_type == "seizure" for entry in active_rights),
        "provisional_seizure": any(entry.right_type == "provisional_seizure" for entry in active_rights),
        "trust": any(entry.right_type == "trust" for entry in active_rights),
    }
    comparisons = [
        FieldComparison(field=field, expected=value, actual=actual.get(field), passed=actual.get(field) == value)
        for field, value in expected.items()
    ]
    matched = sum(item.passed for item in comparisons)
    total = len(comparisons)
    return RegistryEvaluation(
        passed=matched == total,
        matched=matched,
        total=total,
        accuracy=matched / total if total else 1.0,
        comparisons=comparisons,
    )
