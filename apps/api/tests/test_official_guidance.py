from urllib.parse import urlparse

from app.schemas import CheckItem, RiskSignal
from app.services.official_guidance import retrieve_official_guidance


def _signal(signal_id: str, title: str = "확인이 필요한 신호") -> RiskSignal:
    return RiskSignal(
        id=signal_id,
        severity="warning",
        title=title,
        description="테스트 설명",
        evidence="테스트 근거",
        points=10,
    )


def test_trust_signal_prioritizes_hug_trust_guidance():
    result = retrieve_official_guidance(
        signals=[_signal("registry-right-trust", "활성 신탁 등기가 있어요")],
        checks=[CheckItem(label="등기 권리관계", status="warning", detail="활성 신탁")],
        actions=["신탁원부와 수탁자의 임대차 동의서를 확인하세요."],
    )

    assert result[0].id == "hug-trust-consent"
    assert any(source.id == "hug-registry-review" for source in result)


def test_building_review_retrieves_government_ledger_service():
    result = retrieve_official_guidance(
        signals=[],
        checks=[
            CheckItem(
                label="공식 건축물대장",
                status="needs_review",
                detail="건축HUB 응답을 확인하지 못했습니다.",
            )
        ],
        actions=["정부24에서 최신 건축물대장을 다시 발급해 확인하세요."],
    )

    assert result[0].id == "government-building-ledger"


def test_verified_checks_do_not_crowd_out_risk_guidance():
    result = retrieve_official_guidance(
        signals=[_signal("mortgage-present")],
        checks=[
            CheckItem(label="입력 주소와 두 문서", status="verified", detail="일치"),
            CheckItem(label="보증보험 가입", status="needs_review", detail="추가 확인"),
        ],
        actions=["잔금 지급 전 최신 등기부등본을 다시 확인하세요."],
    )

    assert result[0].id == "hug-registry-review"
    assert all(source.id != "hug-contract-crosscheck" for source in result)


def test_catalog_returns_only_curated_official_https_domains():
    result = retrieve_official_guidance(
        signals=[
            _signal("registry-right-trust"),
            _signal("illegal-building"),
            _signal("deposit-market-upper"),
        ],
        checks=[
            CheckItem(label="공식 건축물대장", status="warning", detail="불일치"),
            CheckItem(label="보증보험 가입", status="needs_review", detail="추가 확인"),
        ],
        actions=["신탁원부와 건축물대장, 보증기관을 확인하세요."],
    )

    allowed_domains = {"m.khug.or.kr", "www.khug.or.kr", "www.gov.kr", "www.molit.go.kr"}
    assert result
    assert len(result) <= 3
    assert all(urlparse(source.url).scheme == "https" for source in result)
    assert all(urlparse(source.url).netloc in allowed_domains for source in result)
