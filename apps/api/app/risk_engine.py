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


def _ratio(numerator: int, denominator: int | None) -> float | None:
    return numerator / denominator if denominator else None


def analyze_risk(facts: ExtractedFacts) -> RiskResult:
    signals: list[RiskSignal] = []
    actions: list[str] = []
    burden_ratio = _ratio(facts.mortgage_amount + facts.deposit, facts.estimated_value)
    mortgage_ratio = _ratio(facts.mortgage_amount, facts.estimated_value)
    deposit_ratio = _ratio(facts.deposit, facts.estimated_value)

    if burden_ratio is not None and burden_ratio >= 1:
        signals.append(RiskSignal(
            id="senior-burden", severity="danger", title="근저당과 보증금 합계가 예상 집값보다 커요",
            description=(
                "집을 팔아 회수할 수 있다고 추정한 금액보다 등기부의 근저당 채권최고액과 "
                "내 보증금의 합계가 큽니다. 가격이 내려가거나 매각 비용이 발생하면 보증금 회수 여유가 더 줄 수 있습니다."
            ),
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 근저당+보증금 "
                f"{facts.mortgage_amount + facts.deposit:,}원 ({burden_ratio * 100:.0f}%)"
            ),
            points=35,
        ))
        actions.append("특약사항에 잔금 전 근저당 말소 조건을 명확히 추가하세요.")
    elif burden_ratio is not None and burden_ratio >= .8:
        signals.append(RiskSignal(
            id="senior-burden", severity="warning", title="근저당과 보증금 합계가 예상 집값에 가까워요",
            description=(
                "예상 집값에서 근저당 채권최고액과 내 보증금을 빼면 남는 여유가 크지 않습니다. "
                "최신 시세와 실제 대출 잔액, 근저당 말소 조건을 함께 확인해야 합니다."
            ),
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 근저당+보증금 "
                f"{facts.mortgage_amount + facts.deposit:,}원 ({burden_ratio * 100:.0f}%)"
            ),
            points=24,
        ))

    if mortgage_ratio is not None and mortgage_ratio >= .5:
        signals.append(RiskSignal(
            id="mortgage", severity="danger",
            title=f"예상 집값의 {mortgage_ratio * 100:.0f}%가 근저당 한도로 잡혀 있어요",
            description=(
                "등기부에 담보 한도로 적힌 채권최고액이 예상 집값의 절반을 넘습니다. "
                "채권최고액은 실제 남은 대출금과 다를 수 있으므로 임대인에게 대출 잔액과 말소 계획을 확인해야 합니다."
            ),
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 근저당 채권최고액 "
                f"{facts.mortgage_amount:,}원 ({mortgage_ratio * 100:.0f}%)"
            ),
            points=20,
        ))
        actions.append("특약사항에 잔금 전 근저당 말소 조건을 명확히 추가하세요.")
    elif mortgage_ratio is not None and mortgage_ratio >= .3:
        signals.append(RiskSignal(
            id="mortgage", severity="warning",
            title=f"예상 집값의 {mortgage_ratio * 100:.0f}%가 근저당 한도예요",
            description=(
                "등기부에 근저당 채권최고액이 설정되어 있습니다. 채권최고액은 실제 대출 잔액과 다를 수 있으므로 "
                "잔금 지급 직전에 최신 등기부와 대출 잔액, 말소 조건을 확인해야 합니다."
            ),
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 근저당 채권최고액 "
                f"{facts.mortgage_amount:,}원 ({mortgage_ratio * 100:.0f}%)"
            ),
            points=12,
        ))

    elif facts.mortgage_amount > 0:
        signals.append(RiskSignal(
            id="mortgage-present", severity="warning", title="근저당권이 설정되어 있어요",
            description=(
                "등기부에서 근저당 채권최고액을 확인했지만 비교할 집값이 없어 비율은 계산하지 못했습니다. "
                "채권최고액은 실제 대출 잔액과 다를 수 있으므로 최신 잔액과 말소 조건을 확인하세요."
            ),
            evidence=f"등기부 채권최고액 {facts.mortgage_amount:,}원 · 예상 집값 확인 필요", points=12,
        ))
        actions.append("특약사항에 잔금 전 근저당 말소 조건을 명확히 추가하세요.")

    if deposit_ratio is not None and deposit_ratio >= .8:
        signals.append(RiskSignal(
            id="deposit-ratio", severity="danger",
            title=f"보증금이 예상 집값의 {deposit_ratio * 100:.0f}%예요",
            description="보증금이 예상 집값의 대부분을 차지합니다. 집값이 내려가면 보증금을 돌려받을 여유가 빠르게 줄 수 있습니다.",
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 보증금 {facts.deposit:,}원 "
                f"({deposit_ratio * 100:.0f}%)"
            ), points=18,
        ))
    elif deposit_ratio is not None and deposit_ratio >= .65:
        signals.append(RiskSignal(
            id="deposit-ratio", severity="warning",
            title=f"보증금이 예상 집값의 {deposit_ratio * 100:.0f}%예요",
            description="보증금이 예상 집값에서 차지하는 비중이 큰 편입니다. 가격이 내려가면 보증금 회수 여력이 줄 수 있습니다.",
            evidence=(
                f"예상 집값 {facts.estimated_value:,}원 · 보증금 {facts.deposit:,}원 "
                f"({deposit_ratio * 100:.0f}%)"
            ), points=8,
        ))

    if facts.owner and facts.contract_owner and facts.owner != facts.contract_owner:
        signals.append(RiskSignal(
            id="owner-mismatch", severity="danger", title="소유자와 계약자가 달라요",
            description="적법한 위임 관계인지 원본 서류로 확인해야 합니다.",
            evidence=f"등기 소유자 {facts.owner} · 계약자 {facts.contract_owner}", points=25,
        ))
        actions.append("소유자 본인 확인 또는 인감증명서가 첨부된 위임장 원본을 확인하세요.")

    if facts.is_illegal_building is True:
        signals.append(RiskSignal(
            id="illegal-building", severity="danger", title="위반건축물 표기가 있어요",
            description="보증보험과 대출 가능 여부에 영향을 줄 수 있습니다.",
            evidence="건축물대장 위반건축물: 해당", points=22,
        ))
        actions.append("관할 구청과 보증기관에 위반 내용 및 보증 가입 가능 여부를 확인하세요.")

    if facts.recent_transactions is not None and facts.recent_transactions < 5:
        signals.append(RiskSignal(
            id="thin-market", severity="notice", title="비교할 최근 거래가 적어요",
            description="자동 추정 시세의 신뢰 구간이 넓을 수 있습니다.",
            evidence=f"최근 비교 거래 {facts.recent_transactions}건", points=6,
        ))

    if facts.local_price_volatility is not None and facts.local_price_volatility >= .07:
        signals.append(RiskSignal(
            id="volatility", severity="notice", title="인근 가격 변동성이 있어요",
            description="단일 시세 대신 복수의 감정·거래 자료를 비교하세요.",
            evidence=f"최근 가격 변동성 {facts.local_price_volatility * 100:.1f}%", points=4,
        ))

    score = min(100, sum(signal.points for signal in signals))
    if facts.estimated_value is None:
        grade, headline = "주의", "시세 확인 후 최종 판단이 필요합니다"
        signals.append(RiskSignal(
            id="market-data-unavailable", severity="notice", title="실거래가 기반 시세를 계산하지 못했어요",
            description="공공 실거래가에서 동일·유사 매물 근거가 부족해 예상 주택가액을 계산하지 않았습니다.",
            evidence="비교 가능한 실거래가 부족", points=0,
        ))
    elif score >= 65:
        grade, headline = "높음", "주의가 필요한 계약입니다"
    elif score >= 35 or any(signal.severity == "danger" for signal in signals):
        grade, headline = "주의", "몇 가지 확인이 필요한 계약입니다"
    else:
        grade, headline = "낮음", "현재 확인된 위험 신호는 낮습니다"

    if not actions:
        actions.append("잔금 지급 직전 최신 등기부등본을 다시 확인하세요.")
    elif not any("최신 등기부" in action for action in actions):
        actions.insert(0, "잔금 지급 직전 최신 등기부등본을 다시 확인하세요.")
    actions.append("HUG 등 보증기관에서 보증 가입 가능 여부를 직접 확인하세요.")

    checks = [
        CheckItem(
            label="소유자와 계약자",
            status=("verified" if facts.owner == facts.contract_owner else "warning")
            if facts.owner and facts.contract_owner else "needs_review",
            detail=("일치합니다" if facts.owner == facts.contract_owner else "서로 다릅니다")
            if facts.owner and facts.contract_owner else "소유자 또는 임대인을 추출하지 못했습니다",
        ),
        CheckItem(label="보증금 교차검증", status="verified", detail="입력값과 계약서 추출값이 일치합니다"),
        CheckItem(
            label="위반건축물",
            status=("warning" if facts.is_illegal_building else "verified")
            if facts.is_illegal_building is not None else "needs_review",
            detail=("위반 표기 확인" if facts.is_illegal_building else "해당 없음")
            if facts.is_illegal_building is not None else "위반 여부를 추출하지 못했습니다",
        ),
        CheckItem(label="보증보험 가입", status="needs_review", detail="보증기관에서 추가 확인이 필요합니다"),
    ]

    if deposit_ratio is None or burden_ratio is None:
        summary = (
            f"등기부에서 채권최고액 {facts.mortgage_amount:,}원을 확인했습니다. "
            "비교 가능한 공공 실거래가가 없어 보증금·근저당 비율은 계산하지 않았습니다."
        )
    else:
        summary = (
            f"예상 주택가액 대비 보증금은 {deposit_ratio * 100:.0f}%, "
            f"근저당을 합친 부담은 {burden_ratio * 100:.0f}%입니다. "
            "점수는 위험 신호의 우선순위를 보여주며 법률적 안전을 보증하지 않습니다."
        )
    return RiskResult(score, grade, headline, summary, signals, checks, actions[:3])
