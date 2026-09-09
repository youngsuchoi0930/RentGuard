import asyncio
import json

import httpx
from pydantic import SecretStr

from app.config import Settings
from app.schemas import CheckItem, MarketDataState, RiskSignal
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
        "market_data": MarketDataState(
            status="not_connected",
            message="공공 실거래가 연동 전",
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
        assert request.headers["x-goog-api-key"] == "test-key"
        generated = {
            "overview": "문서끼리 확인된 내용은 서로 일치하지만 주의 신호가 있습니다.",
            "caution": "근저당권은 보증금 회수 가능성에 영향을 줄 수 있어 확인이 필요합니다.",
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
