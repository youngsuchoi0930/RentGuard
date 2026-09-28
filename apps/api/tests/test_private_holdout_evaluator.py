import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_private_holdout import (  # noqa: E402
    _actual_values,
    _baseline_snapshot,
    _compare_baseline,
    _compare_section,
    _document_path,
    _summarize,
)


def test_private_holdout_accepts_private_raw_document_names(tmp_path):
    registry = tmp_path / "registry-original.pdf"
    ledger = tmp_path / "building-ledger-upright-private.pdf"
    registry.write_bytes(b"registry")
    ledger.write_bytes(b"ledger")

    assert _document_path(tmp_path, "registry") == registry
    assert _document_path(tmp_path, "building_ledger") == ledger
    assert _document_path(tmp_path, "lease_contract").name == "lease-contract.pdf"


def test_private_holdout_comparison_normalizes_addresses_and_counts_collection_errors():
    comparisons = _compare_section(
        "registry",
        {
            "owners": ["테스트소유", "테스트공유"],
            "road_address": "서울특별시 테스트구 안전로 123, 201호",
            "mortgages": [
                {
                    "holder": "안전은행",
                    "debtor": "테스트소유",
                    "maximum_claim_amount": 231_000_000,
                }
            ],
            "active_right_types": ["trust", "mortgage"],
        },
        {
            "owners": ["테스트소유", "오탐소유자"],
            "road_address": "서울특별시테스트구안전로123 (안전동), 201호",
            "mortgages": [
                {
                    "holder": "안전은행",
                    "debtor": "테스트소유",
                    "maximum_claim_amount": 231_000_000,
                    "ignored_unlabelled_field": "value",
                }
            ],
            "active_right_types": ["mortgage", "trust"],
        },
    )

    by_field = {item["field"]: item for item in comparisons}
    assert by_field["registry.road_address"]["passed"] is True
    assert by_field["registry.road_address"]["exact_match"] is False
    assert by_field["registry.mortgages"]["passed"] is True
    assert by_field["registry.mortgages"]["exact_match"] is True
    assert by_field["registry.owners"]["passed"] is False
    assert by_field["registry.owners"]["true_positive"] == 1
    assert by_field["registry.owners"]["false_positive"] == 1
    assert by_field["registry.owners"]["false_negative"] == 1


def test_private_holdout_summary_separates_wrong_value_into_false_positive_and_missing():
    comparisons = _compare_section(
        "lease_contract",
        {"deposit": 30_000_000, "monthly_rent": 1_300_000, "tenant": "임차인"},
        {"deposit": 30_000_000, "monthly_rent": 1_000_000, "tenant": None},
    )
    result = _summarize([{"passed": False, "comparisons": comparisons}])

    assert result["matched_fields"] == 1
    assert result["exact_matched_fields"] == 1
    assert result["total_fields"] == 3
    assert result["true_positive_values"] == 1
    assert result["false_positive_values"] == 1
    assert result["false_negative_values"] == 2
    assert result["value_precision"] == 0.5
    assert result["value_recall"] == 1 / 3


def test_private_holdout_captures_active_rights_and_precheck_statuses():
    registry = SimpleNamespace(
        ownership=[SimpleNamespace(owner_name="테스트신탁", status="active")],
        encumbrances=[
            SimpleNamespace(
                right_type="trust",
                status="active",
                holder=None,
                debtor=None,
                maximum_claim_amount=None,
            ),
            SimpleNamespace(
                right_type="mortgage",
                status="cancelled",
                holder="테스트은행",
                debtor="테스트신탁",
                maximum_claim_amount=80_000_000,
            ),
        ],
        property=SimpleNamespace(
            road_address="서울특별시 테스트구 신뢰로 59",
            building_name="테스트빌딩",
            unit="203호",
        ),
    )
    ledger = SimpleNamespace(
        property=SimpleNamespace(
            road_address="서울특별시 테스트구 신뢰로 59",
            lot_address="서울특별시 테스트구 신뢰동 123",
            building_name="테스트빌딩",
            unit="203호",
            exclusive_area=79.97,
            main_use="아파트",
            structure="철근콘크리트구조",
            households=None,
            approval_date=None,
            is_illegal_building=False,
        )
    )
    bundle = SimpleNamespace(cross_checks=[
        SimpleNamespace(id="registry-owner", status="verified"),
        SimpleNamespace(id="property-address", status="verified"),
        SimpleNamespace(id="illegal-building", status="verified"),
    ])

    actual = _actual_values(registry, ledger, None, bundle)

    assert actual["registry"]["active_right_types"] == ["trust"]
    assert actual["registry"]["mortgages"] == []
    assert actual["building_ledger"]["unit"] == "203호"
    assert actual["building_ledger"]["exclusive_area"] == 79.97
    assert actual["cross_checks"]["registry_owner_found"] is True
    assert actual["cross_checks"]["illegal_building_clear"] is True


def test_private_holdout_baseline_contains_no_expected_or_actual_values():
    result = {
        "evaluation_version": "private-holdout-1.1",
        "case_count": 1,
        "total_fields": 2,
        "cases": [{
            "case_id": "CASE-PRIVATE",
            "comparisons": [
                {
                    "field": "registry.owners",
                    "expected": ["민감한이름"],
                    "actual": ["민감한이름"],
                    "passed": True,
                },
                {
                    "field": "registry.road_address",
                    "expected": "민감한주소",
                    "actual": "민감한주소",
                    "passed": True,
                },
            ],
        }],
    }

    baseline = _baseline_snapshot(result)

    assert "민감한이름" not in str(baseline)
    assert "민감한주소" not in str(baseline)
    assert baseline["cases"]["CASE-PRIVATE"]["fields"] == {
        "registry.owners": True,
        "registry.road_address": True,
    }


def test_private_holdout_baseline_detects_missing_case_field_and_failed_field():
    baseline = {
        "total_fields": 3,
        "cases": {
            "CASE-001": {
                "fields": {
                    "registry.owners": True,
                    "registry.road_address": True,
                }
            },
            "CASE-002": {"fields": {"registry.owners": True}},
        },
    }
    current = {
        "total_fields": 1,
        "cases": [{
            "case_id": "CASE-001",
            "comparisons": [{"field": "registry.owners", "passed": False}],
        }],
    }

    comparison = _compare_baseline(baseline, current)

    assert comparison["status"] == "regressed"
    assert comparison["regression_count"] == 4
    assert any("통과하던 필드" in item for item in comparison["regressions"])
    assert any("기준 필드" in item for item in comparison["regressions"])
    assert any("기준 사례" in item for item in comparison["regressions"])
    assert any("라벨 필드 수" in item for item in comparison["regressions"])
