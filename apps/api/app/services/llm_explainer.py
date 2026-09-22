from __future__ import annotations

import json
import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..config import Settings, get_settings
from ..schemas import (
    AIExplanation,
    CheckItem,
    DepositMarketState,
    MarketDataState,
    OfficialGuidanceSource,
    RiskSignal,
)
from .official_guidance import retrieve_official_guidance


class _GeneratedExplanation(BaseModel):
    overview: str = Field(min_length=10, max_length=350)
    caution: str = Field(min_length=10, max_length=350)
    limitation: str = Field(min_length=10, max_length=350)


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {
            "type": "string",
            "description": "현재 문서 분석 상태를 쉬운 한국어로 요약한 한두 문장",
        },
        "caution": {
            "type": "string",
            "description": "규칙 엔진의 행동 목록을 바탕으로 사용자가 지금 할 수 있는 확인 팁 한두 문장",
        },
        "limitation": {
            "type": "string",
            "description": "이 분석이 판단하지 못한 범위를 설명한 한 문장",
        },
    },
    "required": ["overview", "caution", "limitation"],
    "additionalProperties": False,
}

_FORBIDDEN_CERTAINTY = (
    "안전합니다",
    "안전한 계약",
    "계약해도 됩니다",
    "문제없습니다",
    "보장합니다",
    "확실합니다",
)

_SYSTEM_INSTRUCTION = """당신은 주택 임대차 계약을 판단하는 심사자가 아니라, RentGuard가 확인한 정보를 쉽게 설명하는 조언 도우미입니다.
판단과 점수는 규칙 엔진과 연결된 공공데이터가 이미 확정했으므로 절대 새로 계산하거나 변경하지 마세요.
입력 JSON에 없는 사실, 수치, 금액, 인물, 주소, 법률 결론을 만들지 마세요.
출력 문장에는 숫자, 금액, 백분율을 쓰지 마세요.
안전을 보장하거나 계약 진행을 권하는 단정적 표현을 쓰지 마세요.
overview에서는 확인된 신호와 공공데이터 상태만 요약하세요.
caution에서는 recommended_actions에 있는 행동만 쉬운 확인 팁으로 바꿔 말하고, 목록에 없는 조언을 새로 만들지 마세요.
limitation에서는 확인하지 못한 데이터와 이 설명이 법률 판단이 아니라는 한계를 밝히세요.
official_guidance에 있는 공식자료 요약만 참고하고, 그 요약에 없는 제도·자격·법률 내용을 만들지 마세요.
공식자료를 근거로 한 팁도 recommended_actions의 범위를 벗어나면 안 됩니다.
공공데이터가 unavailable 또는 needs_review이면 확인했다고 표현하지 마세요."""


def _safe_payload(
    *,
    grade: str,
    signals: Sequence[RiskSignal],
    checks: Sequence[CheckItem],
    actions: Sequence[str],
    market_data: MarketDataState,
    deposit_market: DepositMarketState,
    official_guidance: Sequence[OfficialGuidanceSource],
) -> dict[str, object]:
    """Build the only data shape allowed to leave the RentGuard server.

    Raw documents, evidence snippets, names, addresses, and monetary values are
    deliberately absent. Keep this allowlist narrow when adding new fields.
    """
    official_building = next(
        (check for check in checks if check.label == "공식 건축물대장"),
        None,
    )
    return {
        "grade": grade,
        "connected_data": [
            {
                "source": "건축HUB 공식 건축물대장",
                "status": official_building.status if official_building else "needs_review",
            },
            {
                "source": market_data.source or "국토교통부 매매 실거래가",
                "status": market_data.status,
            },
            {
                "source": deposit_market.source,
                "status": deposit_market.status,
                "range_result": (
                    "above_expected_range"
                    if deposit_market.exceeds_upper is True
                    else "within_expected_range"
                    if deposit_market.exceeds_upper is False
                    else "not_determined"
                ),
            },
        ],
        "signals": [
            {"id": signal.id, "severity": signal.severity, "title": signal.title}
            for signal in signals
        ],
        "checks": [
            {
                "label": check.label,
                "status": check.status,
                "comparisons": [
                    {"label": comparison.label, "status": comparison.status}
                    for comparison in check.comparisons
                ],
            }
            for check in checks
        ],
        "recommended_actions": list(actions),
        "official_guidance": [source.model_dump() for source in official_guidance],
    }


def _is_safe_output(content: _GeneratedExplanation) -> bool:
    combined = " ".join((content.overview, content.caution, content.limitation))
    if re.search(r"\d", combined):
        return False
    return not any(phrase in combined for phrase in _FORBIDDEN_CERTAINTY)


def _unavailable(
    *,
    model: str,
    status: str = "unavailable",
    message: str = "AI 쉬운 설명을 불러오지 못해 규칙 기반 결과만 표시합니다.",
    sources: Sequence[OfficialGuidanceSource] = (),
) -> AIExplanation:
    return AIExplanation(
        status=status,  # type: ignore[arg-type]
        provider="gemini",
        model=model,
        message=message,
        sources=list(sources),
    )


async def generate_gemini_explanation(
    *,
    grade: str,
    signals: Sequence[RiskSignal],
    checks: Sequence[CheckItem],
    actions: Sequence[str],
    market_data: MarketDataState,
    deposit_market: DepositMarketState,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> AIExplanation:
    resolved = settings or get_settings()
    official_guidance = retrieve_official_guidance(
        signals=signals,
        checks=checks,
        actions=actions,
    )
    if resolved.gemini_api_key is None:
        return _unavailable(
            model=resolved.gemini_model,
            status="disabled",
            sources=official_guidance,
        )

    safe_input = _safe_payload(
        grade=grade,
        signals=signals,
        checks=checks,
        actions=actions,
        market_data=market_data,
        deposit_market=deposit_market,
        official_guidance=official_guidance,
    )
    request_body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "다음 비식별 분석 결과와 연결 데이터 상태만 근거로 정보 기반 확인 팁을 작성하세요.\n"
                        + json.dumps(safe_input, ensure_ascii=False)
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 350,
            "responseMimeType": "application/json",
            "responseJsonSchema": _OUTPUT_SCHEMA,
        },
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{resolved.gemini_model}:generateContent"
    )
    owns_client = client is None
    request_client = client or httpx.AsyncClient(
        timeout=resolved.gemini_timeout_seconds
    )
    try:
        response = await request_client.post(
            url,
            headers={
                "x-goog-api-key": resolved.gemini_api_key.get_secret_value(),
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        payload = response.json()
        parts = payload["candidates"][0]["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts)
        generated = _GeneratedExplanation.model_validate_json(text)
        if not _is_safe_output(generated):
            return _unavailable(
                model=resolved.gemini_model,
                sources=official_guidance,
            )
        return AIExplanation(
            status="generated",
            provider="gemini",
            model=resolved.gemini_model,
            overview=generated.overview,
            caution=generated.caution,
            limitation=generated.limitation,
            privacy_note="Gemini는 판단에 관여하지 않으며 원본 문서·주소·이름·금액을 전송하지 않았습니다.",
            sources=official_guidance,
        )
    except httpx.TimeoutException:
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini 응답 시간이 초과되어 규칙 기반 결과만 표시합니다. 잠시 후 다시 분석해주세요.",
            sources=official_guidance,
        )
    except httpx.HTTPStatusError as exc:
        return _unavailable(
            model=resolved.gemini_model,
            message=f"Gemini API가 오류({exc.response.status_code})를 반환해 규칙 기반 결과만 표시합니다.",
            sources=official_guidance,
        )
    except httpx.HTTPError:
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini API에 연결하지 못해 규칙 기반 결과만 표시합니다.",
            sources=official_guidance,
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini 응답 형식을 확인하지 못해 규칙 기반 결과만 표시합니다.",
            sources=official_guidance,
        )
    finally:
        if owns_client:
            await request_client.aclose()
