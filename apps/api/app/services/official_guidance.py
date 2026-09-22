from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from ..schemas import CheckItem, OfficialGuidanceSource, RiskSignal


@dataclass(frozen=True)
class _CatalogEntry:
    source: OfficialGuidanceSource
    signal_ids: frozenset[str] = frozenset()
    signal_prefixes: tuple[str, ...] = ()
    check_keywords: tuple[str, ...] = ()
    action_keywords: tuple[str, ...] = ()
    fallback: bool = False


_CATALOG = (
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="hug-trust-consent",
            organization="주택도시보증공사(HUG)",
            title="신탁회사의 동의 없는 계약 확인사항",
            url="https://m.khug.or.kr/jeonse/web/s02/s020302.jsp",
            summary="등기부 갑구에서 신탁 여부를 확인하고, 신탁원부와 수탁자의 임대차 동의 여부를 계약 전에 확인하도록 안내합니다.",
        ),
        signal_ids=frozenset({"registry-right-trust"}),
        check_keywords=("신탁",),
        action_keywords=("신탁원부", "수탁자", "동의서"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="hug-registry-review",
            organization="주택도시보증공사(HUG)",
            title="등기부등본 확인 방법",
            url="https://m.khug.or.kr/jeonse/web/s03/s030105.jsp",
            summary="등기부 갑구와 을구에서 소유권 제한, 근저당권, 전세권, 임차권 등을 확인하고 말소사항 포함 발급본으로 권리 변동을 살피도록 안내합니다.",
        ),
        signal_ids=frozenset({"mortgage", "mortgage-present", "senior-burden"}),
        signal_prefixes=("registry-right-",),
        check_keywords=("등기 권리관계",),
        action_keywords=("등기부", "근저당", "말소", "압류", "가압류", "전세권", "임차권", "경매"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="hug-guarantee-overview",
            organization="주택도시보증공사(HUG)",
            title="전세보증금반환보증 상품개요",
            url="https://www.khug.or.kr/hug/web/ig/dr/igdr000001.jsp",
            summary="보증 신청 조건과 주택가격, 선순위채권, 보증금의 관계 등 반환보증 가입 심사에 필요한 주요 요건을 안내합니다.",
        ),
        check_keywords=("보증보험 가입",),
        action_keywords=("보증기관", "보증 가입", "HUG"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="hug-contract-crosscheck",
            organization="주택도시보증공사(HUG)",
            title="임대차 계약내용 확인 방법",
            url="https://m.khug.or.kr/jeonse/web/s03/s030205.jsp",
            summary="계약서의 소재지와 면적은 등기부·건축물대장과, 계약 당사자는 신분증과 서로 일치하는지 확인하도록 안내합니다.",
        ),
        check_keywords=("소유자", "계약자", "임대인", "주소", "보증금", "월세"),
        action_keywords=("계약서", "임대인", "소유자"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="government-building-ledger",
            organization="정부24",
            title="건축물대장 발급·열람",
            url="https://www.gov.kr/mw/AA020InfoCappView.do?CappBizCD=15000000098&tp_seq=03",
            summary="정부24에서 최신 건축물대장을 발급하거나 열람하여 용도, 면적, 위반건축물 표시 등 원문 기재사항을 직접 확인할 수 있습니다.",
        ),
        signal_ids=frozenset({"illegal-building"}),
        check_keywords=("건축물대장", "위반건축물"),
        action_keywords=("건축물대장", "정부24", "세움터"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="hug-price-check",
            organization="주택도시보증공사(HUG)",
            title="주택가격과 보증금 확인 방법",
            url="https://m.khug.or.kr/jeonse/web/s03/s030104.jsp",
            summary="계약 전 주택가격과 보증금 수준을 확인하여 보증금 반환 위험을 살피는 방법과 확인 경로를 안내합니다.",
        ),
        signal_ids=frozenset({"senior-burden", "deposit-ratio", "deposit-market-upper", "thin-market", "volatility", "market-data-unavailable"}),
        action_keywords=("시세", "실거래", "주택가액", "보증금"),
    ),
    _CatalogEntry(
        source=OfficialGuidanceSource(
            id="molit-contract-checklist",
            organization="국토교통부",
            title="안심 전세계약 체크리스트",
            url="https://www.molit.go.kr/USR/NEWS/m_71/dtl.jsp?id=95091157&lcmspage=34",
            summary="계약 전·계약 시·계약 후 단계별로 권리관계, 적정 시세, 계약 당사자, 신고와 확정일자 등을 확인하는 공식 체크리스트입니다.",
        ),
        fallback=True,
    ),
)


def _contains_any(texts: Iterable[str], keywords: tuple[str, ...]) -> bool:
    combined = " ".join(texts)
    return any(keyword.lower() in combined.lower() for keyword in keywords)


def retrieve_official_guidance(
    *,
    signals: Sequence[RiskSignal],
    checks: Sequence[CheckItem],
    actions: Sequence[str],
    limit: int = 3,
) -> list[OfficialGuidanceSource]:
    """Return deterministic, curated official guidance for the current result.

    Only check items that are unresolved or warnings influence retrieval. This
    prevents a verified check from crowding out guidance for an actual risk.
    """
    signal_ids = {signal.id for signal in signals}
    unresolved_labels = [
        check.label for check in checks if check.status in {"warning", "needs_review"}
    ]
    ranked: list[tuple[int, int, OfficialGuidanceSource]] = []
    for index, entry in enumerate(_CATALOG):
        score = 0
        score += 100 * len(signal_ids & entry.signal_ids)
        score += 80 * sum(
            any(signal_id.startswith(prefix) for prefix in entry.signal_prefixes)
            for signal_id in signal_ids
        )
        if _contains_any(unresolved_labels, entry.check_keywords):
            score += 45
        if _contains_any(actions, entry.action_keywords):
            score += 25
        if entry.fallback:
            score += 1
        if score:
            ranked.append((score, -index, entry.source))
    ranked.sort(reverse=True, key=lambda item: (item[0], item[1]))
    return [source for _, _, source in ranked[:limit]]
