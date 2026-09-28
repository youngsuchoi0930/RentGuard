import ast
import json
from pathlib import Path

import pytest

from app.risk_engine import (
    RISK_POLICY_VERSION,
    RISK_SCORE_CAP,
    analyze_risk,
)
from app.schemas import ExtractedFacts
from app.services.analysis_service import _REGISTRY_RIGHT_RULES


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = ROOT / "docs" / "risk-policy-v2.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _facts(**overrides) -> ExtractedFacts:
    values = {
        "owner": "소유자",
        "contract_owner": "소유자",
        "mortgage_amount": 0,
        "deposit": 10_000_000,
        "monthly_rent": 0,
        "estimated_value": 100_000_000,
        "is_illegal_building": False,
        "recent_transactions": 20,
        "local_price_volatility": 0.01,
    }
    values.update(overrides)
    return ExtractedFacts(**values)


def _rule(key: str) -> dict:
    return next(rule for rule in _manifest()["rules"] if rule["key"] == key)


@pytest.mark.parametrize(
    ("rule_key", "overrides"),
    [
        ("senior-burden-danger", {"mortgage_amount": 20_000_000, "deposit": 80_000_000}),
        ("senior-burden-warning", {"mortgage_amount": 10_000_000, "deposit": 70_000_000}),
        ("mortgage-danger", {"mortgage_amount": 50_000_000, "deposit": 0}),
        ("mortgage-warning", {"mortgage_amount": 30_000_000, "deposit": 0}),
        ("mortgage-market-unavailable", {"mortgage_amount": 1_000_000, "estimated_value": None}),
        ("deposit-ratio-danger", {"deposit": 80_000_000}),
        ("deposit-ratio-warning", {"deposit": 65_000_000}),
        ("owner-mismatch", {"contract_owner": "다른 임대인"}),
        ("illegal-building", {"is_illegal_building": True}),
        ("thin-market", {"recent_transactions": 4}),
        ("volatility", {"local_price_volatility": 0.07}),
        ("market-data-unavailable", {"estimated_value": None}),
    ],
)
def test_documented_core_rule_matches_runtime(rule_key, overrides):
    policy = _rule(rule_key)
    result = analyze_risk(_facts(**overrides))
    matches = [
        signal
        for signal in result.signals
        if signal.id == policy["signal_id"]
        and signal.points == policy["points"]
        and signal.severity == policy["severity"]
    ]

    assert matches, f"runtime rule drifted from {rule_key}"
    if policy["action"]:
        assert policy["action"] in result.actions


def test_registry_right_policy_matches_runtime_rule_table():
    manifest_rules = {rule["key"]: rule for rule in _manifest()["rules"]}

    for right_type, runtime in _REGISTRY_RIGHT_RULES.items():
        documented = manifest_rules[f"registry-right-{right_type.replace('_', '-')}"]
        assert documented["signal_id"] == f"registry-right-{right_type}"
        assert documented["severity"] == runtime["severity"]
        assert documented["points"] == runtime["points"]
        assert documented["action"] == runtime["action"]


def _literal_signal_ids(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "RiskSignal":
            continue
        for keyword in node.keywords:
            if keyword.arg == "id" and isinstance(keyword.value, ast.Constant):
                if isinstance(keyword.value.value, str):
                    values.add(keyword.value.value)
    return values


def test_manifest_covers_every_runtime_signal_id():
    documented_ids = {rule["signal_id"] for rule in _manifest()["rules"]}
    runtime_ids = _literal_signal_ids(ROOT / "apps" / "api" / "app" / "risk_engine.py")
    runtime_ids |= _literal_signal_ids(
        ROOT / "apps" / "api" / "app" / "services" / "analysis_service.py"
    )
    runtime_ids |= {f"registry-right-{right_type}" for right_type in _REGISTRY_RIGHT_RULES}

    assert documented_ids == runtime_ids


def test_policy_metadata_and_references_are_consistent():
    manifest = _manifest()
    reference_ids = {reference["id"] for reference in manifest["official_references"]}

    assert manifest["policy_version"] == RISK_POLICY_VERSION
    assert manifest["score_model"]["score_cap"] == RISK_SCORE_CAP
    assert all(reference["url"].startswith("https://") for reference in manifest["official_references"])
    assert all(
        set(rule["reference_ids"]) <= reference_ids
        for rule in manifest["rules"]
    )


def test_score_cap_and_action_deduplication_are_enforced():
    result = analyze_risk(_facts(
        owner="소유자",
        contract_owner="다른 임대인",
        mortgage_amount=60_000_000,
        deposit=80_000_000,
        is_illegal_building=True,
        recent_transactions=1,
        local_price_volatility=0.2,
    ))

    assert result.score == RISK_SCORE_CAP
    assert len(result.actions) <= _manifest()["action_policy"]["maximum"]
    assert len(result.actions) == len(set(result.actions))
