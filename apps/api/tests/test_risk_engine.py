from app.risk_engine import analyze_risk
from app.schemas import ExtractedFacts


def make_facts(**overrides):
    values = dict(
        owner="김민준", contract_owner="김민준", mortgage_amount=110_000_000,
        deposit=150_000_000, estimated_value=220_000_000, building_use="다세대주택",
        is_illegal_building=False, approval_year=2017, recent_transactions=3,
        local_price_volatility=.08,
    )
    values.update(overrides)
    return ExtractedFacts(**values)


def test_demo_contract_is_high_risk():
    result = analyze_risk(make_facts())
    assert result.score == 73
    assert result.grade == "높음"
    assert result.signals[0].id == "senior-burden"
    assert len(result.actions) == 3


def test_safe_contract_stays_low():
    result = analyze_risk(make_facts(
        mortgage_amount=0, deposit=80_000_000, estimated_value=220_000_000,
        recent_transactions=20, local_price_volatility=.02,
    ))
    assert result.score == 0
    assert result.grade == "낮음"


def test_owner_mismatch_is_flagged():
    result = analyze_risk(make_facts(contract_owner="박서준"))
    assert any(signal.id == "owner-mismatch" for signal in result.signals)
    assert result.checks[0].status == "warning"
