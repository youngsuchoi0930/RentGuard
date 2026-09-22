import asyncio
import json

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.schemas import CheckItem, DepositMarketState, MarketDataState, RiskSignal
from app.services.llm_explainer import generate_gemini_explanation


def _settings() -> Settings:
    return Settings(
        GEMINI_API_KEY=SecretStr("test-key"),
        GEMINI_MODEL="gemini-3.5-flash-lite",
    )


def _inputs():
    return {
        "grade": "주의",
        "signals": [
            RiskSignal(
                id="mortgage-present",
                severity="warning",
                title="근저당권이 설정되어 있어요",
                description="서버 내부 설명",
                evidence="채권최고액 110,000,000원",
                points=12,
            )
        ],
        "checks": [
            CheckItem(
                label="소유자와 계약자",
                status="verified",
                detail="홍길동과 홍길동이 일치합니다",
            )
        ],
        "actions": ["잔금 지급 전 최신 등기부등본을 다시 확인하세요."],
        "market_data": MarketDataState(
            status="not_connected",
            message="공공 실거래가 연동 전",
        ),
        "deposit_market": DepositMarketState(
            status="available",
            message="예측 범위 안",
            expected_deposit=50_000_000,
            upper_deposit=100_000_000,
            upper_ratio=1.0,
            exceeds_upper=False,
        ),
    }


def test_gemini_explainer_sends_only_allowlisted_non_personal_data():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        prompt = body["contents"][0]["parts"][0]["text"]
        assert "홍길동" not in prompt
        assert "110,000,000" not in prompt
        assert "evidence" not in prompt
        assert "description" not in prompt
        assert "recommended_actions" in prompt
        assert "잔금 지급 전 최신 등기부등본을 다시 확인하세요." in prompt
        assert "건축HUB 공식 건축물대장" in prompt
        assert "within_expected_range" in prompt
        assert "심사자가 아니라" in body["systemInstruction"]["parts"][0]["text"]
        assert "목록에 없는 조언을 새로 만들지 마세요" in body["systemInstruction"]["parts"][0]["text"]
        assert request.headers["x-goog-api-key"] == "test-key"
        generated = {
            "overview": "문서끼리 확인된 내용은 서로 일치하지만 주의 신호가 있습니다.",
            "caution": "잔금을 보내기 전에 최신 등기부를 다시 발급해 권리 변동이 없는지 확인하세요.",
            "limitation": "시세 자료가 없어 전체 부담 수준은 아직 판단할 수 없습니다.",
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await generate_gemini_explanation(
                **_inputs(), settings=_settings(), client=client
            )

    result = asyncio.run(run())
    assert result.status == "generated"
    assert result.provider == "gemini"
    assert result.privacy_note is not None
    assert "판단에 관여하지 않으며" in result.privacy_note


def test_gemini_explainer_rejects_new_numbers():
    def handler(request: httpx.Request) -> httpx.Response:
        generated = {
            "overview": "위험 점수는 99점입니다.",
            "caution": "확인이 필요한 위험 신호가 있습니다.",
            "limitation": "시세 자료가 없어 최종 판단은 어렵습니다.",
        }
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": json.dumps(generated, ensure_ascii=False)}]}}
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await generate_gemini_explanation(
                **_inputs(), settings=_settings(), client=client
            )

    result = asyncio.run(run())
    assert result.status == "unavailable"
    assert result.overview is None


def test_gemini_explainer_reports_timeout_reason():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await generate_gemini_explanation(
                **_inputs(), settings=_settings(), client=client
            )

    result = asyncio.run(run())
    assert result.status == "unavailable"
    assert result.message is not None
    assert "시간이 초과" in result.message
