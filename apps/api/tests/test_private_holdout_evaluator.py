import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_private_holdout import _actual_values, _compare_section, _summarize  # noqa: E402


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
        property=SimpleNamespace(road_address="서울특별시 테스트구 신뢰로 59"),
    )
    ledger = SimpleNamespace(
        property=SimpleNamespace(
            road_address="서울특별시 테스트구 신뢰로 59",
            building_name="테스트빌딩",
            main_use="아파트",
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
    assert actual["cross_checks"]["registry_owner_found"] is True
    assert actual["cross_checks"]["illegal_building_clear"] is True
