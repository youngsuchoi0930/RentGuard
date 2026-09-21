import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_private_holdout import _compare_section, _summarize  # noqa: E402


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
