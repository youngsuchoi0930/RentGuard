from dataclasses import dataclass

from .schemas import CheckItem, ExtractedFacts, RiskSignal


@dataclass(frozen=True)
class RiskResult:
    score: int
    grade: str
    headline: str
    summary: str
    signals: list[RiskSignal]
    checks: list[CheckItem]
    actions: list[str]


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0


def analyze_risk(facts: ExtractedFacts) -> RiskResult:
    signals: list[RiskSignal] = []
    actions: list[str] = []
    burden_ratio = _ratio(facts.mortgage_amount + facts.deposit, facts.estimated_value)
    mortgage_ratio = _ratio(facts.mortgage_amount, facts.estimated_value)
    deposit_ratio = _ratio(facts.deposit, facts.estimated_value)

    if burden_ratio >= 1:
        signals.append(RiskSignal(
            id="senior-burden", severity="danger", title="선순위 부담 비율이 높아요",
            description="근저당 채권최고액과 보증금의 합이 예상 주택가액을 넘습니다.",
            evidence=f"예상 부담 비율 {burden_ratio * 100:.0f}%", points=35,
        ))
        actions.append("특약사항에 잔금 전 근저당 말소 조건을 명확히 추가하세요.")
    elif burden_ratio >= .8:
        signals.append(RiskSignal(
            id="senior-burden", severity="warning", title="선순위 부담을 확인해야 해요",
            description="근저당과 보증금을 합친 금액이 주택가액에 근접합니다.",
            evidence=f"예상 부담 비율 {burden_ratio * 100:.0f}%", points=24,
        ))

    if mortgage_ratio >= .5:
        signals.append(RiskSignal(
            id="mortgage", severity="danger", title="근저당 설정액이 큽니다",
            description="등기부상 채권최고액이 예상 주택가액의 절반 이상입니다.",
            evidence=f"근저당 비율 {mortgage_ratio * 100:.0f}%", points=20,
        ))
    elif mortgage_ratio >= .3:
        signals.append(RiskSignal(
            id="mortgage", severity="warning", title="근저당 설정을 확인하세요",
            description="잔금 지급 직전 최신 등기부로 변동 여부를 확인해야 합니다.",
            evidence=f"근저당 비율 {mortgage_ratio * 100:.0f}%", points=12,
        ))

    if deposit_ratio >= .8:
        signals.append(RiskSignal(
            id="deposit-ratio", severity="danger", title="보증금 비율이 높아요",
            description="보증금이 예상 주택가액의 80% 이상입니다.",
            evidence=f"보증금 비율 {deposit_ratio * 100:.0f}%", points=18,
        ))
    elif deposit_ratio >= .65:
        signals.append(RiskSignal(
            id="deposit-ratio", severity="warning", title="보증금이 시세에 가까워요",
            description="가격 하락 시 보증금 회수 여력이 줄어들 수 있습니다.",
            evidence=f"보증금 비율 {deposit_ratio * 100:.0f}%", points=8,
        ))

    if facts.owner != facts.contract_owner:
        signals.append(RiskSignal(
            id="owner-mismatch", severity="danger", title="소유자와 계약자가 달라요",
            description="적법한 위임 관계인지 원본 서류로 확인해야 합니다.",
            evidence=f"등기 소유자 {facts.owner} · 계약자 {facts.contract_owner}", points=25,
        ))
        actions.append("소유자 본인 확인 또는 인감증명서가 첨부된 위임장 원본을 확인하세요.")

    if facts.is_illegal_building:
        signals.append(RiskSignal(
            id="illegal-building", severity="danger", title="위반건축물 표기가 있어요",
            description="보증보험과 대출 가능 여부에 영향을 줄 수 있습니다.",
            evidence="건축물대장 위반건축물: 해당", points=22,
        ))
        actions.append("관할 구청과 보증기관에 위반 내용 및 보증 가입 가능 여부를 확인하세요.")

    if facts.recent_transactions < 5:
        signals.append(RiskSignal(
            id="thin-market", severity="notice", title="비교할 최근 거래가 적어요",
            description="자동 추정 시세의 신뢰 구간이 넓을 수 있습니다.",
            evidence=f"최근 비교 거래 {facts.recent_transactions}건", points=6,
        ))

    if facts.local_price_volatility >= .07:
        signals.append(RiskSignal(
            id="volatility", severity="notice", title="인근 가격 변동성이 있어요",
            description="단일 시세 대신 복수의 감정·거래 자료를 비교하세요.",
            evidence=f"최근 가격 변동성 {facts.local_price_volatility * 100:.1f}%", points=4,
        ))

    score = min(100, sum(signal.points for signal in signals))
    if score >= 65:
        grade, headline = "높음", "주의가 필요한 계약입니다"
    elif score >= 35:
        grade, headline = "주의", "몇 가지 확인이 필요한 계약입니다"
    else:
        grade, headline = "낮음", "현재 확인된 위험 신호는 낮습니다"

    if not actions:
        actions.append("잔금 지급 직전 최신 등기부등본을 다시 확인하세요.")
    elif not any("최신 등기부" in action for action in actions):
        actions.insert(0, "잔금 지급 직전 최신 등기부등본을 다시 확인하세요.")
    actions.append("HUG 등 보증기관에서 보증 가입 가능 여부를 직접 확인하세요.")

    checks = [
        CheckItem(label="소유자와 계약자", status="verified" if facts.owner == facts.contract_owner else "warning",
                  detail="일치합니다" if facts.owner == facts.contract_owner else "서로 다릅니다"),
        CheckItem(label="보증금 교차검증", status="verified", detail="입력값과 계약서 추출값이 일치합니다"),
        CheckItem(label="위반건축물", status="verified" if not facts.is_illegal_building else "warning",
                  detail="해당 없음" if not facts.is_illegal_building else "위반 표기 확인"),
        CheckItem(label="보증보험 가입", status="needs_review", detail="보증기관에서 추가 확인이 필요합니다"),
    ]

    summary = (
        f"예상 주택가액 대비 보증금은 {deposit_ratio * 100:.0f}%, "
        f"근저당을 합친 부담은 {burden_ratio * 100:.0f}%입니다. "
        "점수는 위험 신호의 우선순위를 보여주며 법률적 안전을 보증하지 않습니다."
    )
    return RiskResult(score, grade, headline, summary, signals, checks, actions[:3])
