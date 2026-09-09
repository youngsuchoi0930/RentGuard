from __future__ import annotations

import json
import re
from collections.abc import Sequence

import httpx
from pydantic import BaseModel, Field, ValidationError

from ..config import Settings, get_settings
from ..schemas import AIExplanation, CheckItem, MarketDataState, RiskSignal


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
            "description": "확인된 위험 신호가 왜 중요한지 설명한 한두 문장",
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

_SYSTEM_INSTRUCTION = """당신은 주택 임대차 문서 분석 결과를 쉬운 한국어로 풀어쓰는 설명 도우미입니다.
판단과 점수는 이미 규칙 엔진이 확정했으므로 절대 새로 계산하거나 변경하지 마세요.
입력 JSON에 없는 사실, 수치, 금액, 인물, 주소, 법률 결론을 만들지 마세요.
출력 문장에는 숫자, 금액, 백분율을 쓰지 마세요.
안전을 보장하거나 계약 진행을 권하는 단정적 표현을 쓰지 마세요.
위험 신호와 검증 상태의 의미, 그리고 분석의 한계만 차분하고 간결하게 설명하세요."""


def _safe_payload(
    *,
    grade: str,
    signals: Sequence[RiskSignal],
    checks: Sequence[CheckItem],
    market_data: MarketDataState,
) -> dict[str, object]:
    """Build the only data shape allowed to leave the RentGuard server.

    Raw documents, evidence snippets, names, addresses, and monetary values are
    deliberately absent. Keep this allowlist narrow when adding new fields.
    """
    return {
        "grade": grade,
        "market_data_status": market_data.status,
        "signals": [
            {"id": signal.id, "severity": signal.severity, "title": signal.title}
            for signal in signals
        ],
        "checks": [
            {"label": check.label, "status": check.status}
            for check in checks
        ],
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
) -> AIExplanation:
    return AIExplanation(
        status=status,  # type: ignore[arg-type]
        provider="gemini",
        model=model,
        message=message,
    )


async def generate_gemini_explanation(
    *,
    grade: str,
    signals: Sequence[RiskSignal],
    checks: Sequence[CheckItem],
    market_data: MarketDataState,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> AIExplanation:
    resolved = settings or get_settings()
    if resolved.gemini_api_key is None:
        return _unavailable(model=resolved.gemini_model, status="disabled")

    safe_input = _safe_payload(
        grade=grade,
        signals=signals,
        checks=checks,
        market_data=market_data,
    )
    request_body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "다음 비식별 분석 결과만 설명하세요.\n"
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
            return _unavailable(model=resolved.gemini_model)
        return AIExplanation(
            status="generated",
            provider="gemini",
            model=resolved.gemini_model,
            overview=generated.overview,
            caution=generated.caution,
            limitation=generated.limitation,
            privacy_note="원본 문서·주소·이름·금액을 Gemini에 전송하지 않았습니다.",
        )
    except httpx.TimeoutException:
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini 응답 시간이 초과되어 규칙 기반 결과만 표시합니다. 잠시 후 다시 분석해주세요.",
        )
    except httpx.HTTPStatusError as exc:
        return _unavailable(
            model=resolved.gemini_model,
            message=f"Gemini API가 오류({exc.response.status_code})를 반환해 규칙 기반 결과만 표시합니다.",
        )
    except httpx.HTTPError:
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini API에 연결하지 못해 규칙 기반 결과만 표시합니다.",
        )
    except (KeyError, TypeError, ValueError, ValidationError):
        return _unavailable(
            model=resolved.gemini_model,
            message="Gemini 응답 형식을 확인하지 못해 규칙 기반 결과만 표시합니다.",
        )
    finally:
        if owns_client:
            await request_client.aclose()
