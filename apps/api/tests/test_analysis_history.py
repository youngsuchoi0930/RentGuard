from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.schemas import AIExplanation, AnalysisFeedbackCreate, RiskSignal
from app.services.analysis_history import (
    AnalysisFeedbackRecord,
    AnalysisRecord,
    AnalysisHistoryStore,
    mask_address,
)
from app.services.analysis_service import build_analysis
from app.services.building_parser import extract_building_ledger
from app.services.lease_parser import extract_lease_contract
from app.services.registry_parser import extract_registry


client = TestClient(app)


def _analysis():
    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    return build_analysis(
        address="서울특별시 강서구 화곡로 123, 301호",
        deposit=150_000_000,
        monthly_rent=100_000,
        registry=extract_registry(
            (fixtures / "registry_risky_digital.pdf").read_bytes()
        ),
        building_ledger=extract_building_ledger(
            (fixtures / "building_ledger_risky.pdf").read_bytes()
        ),
        lease_contract=extract_lease_contract(
            (fixtures / "lease_contract_risky.pdf").read_bytes()
        ),
    )


def test_mask_address_keeps_only_region():
    assert mask_address("서울특별시 강서구 화곡로 123, 301호") == (
        "서울특별시 강서구 · 상세주소 비공개"
    )
    assert mask_address("화곡동") == "주소 비공개"


def test_store_removes_names_document_evidence_and_exact_address(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis = _analysis()
    analysis.signals.append(
        RiskSignal(
            id="privacy-regression",
            severity="warning",
            title="김민준 확인 필요",
            description="서울특별시 강서구 화곡로 123, 301호를 확인하세요.",
            evidence="등기 소유자 김민준",
            points=0,
        )
    )
    analysis.ai_explanation = AIExplanation(
        status="generated",
        provider="gemini",
        model="test-model",
        overview="김민준 관련 분석입니다.",
    )

    stored = store.save("서울특별시 강서구 화곡로 123, 301호", analysis)
    loaded = store.get(analysis.analysis_id)

    assert loaded is not None
    assert loaded == stored
    assert loaded.masked_address == "서울특별시 강서구 · 상세주소 비공개"
    assert loaded.facts.owner is None
    assert loaded.facts.contract_owner is None
    assert all(not signal.sources for signal in loaded.signals)
    assert all(not check.sources for check in loaded.checks)

    with store.sessions() as session:
        payload = session.get(AnalysisRecord, analysis.analysis_id).payload_json
    assert "김민준" not in payload
    assert "화곡로 123" not in payload
    assert "[개인정보 비공개]" in payload
    assert '"documents"' not in payload
    assert '"raw_text"' not in payload
    store.engine.dispose()


def test_store_lists_newest_and_deletes_record(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis = _analysis()
    store.save("서울특별시 강서구 화곡로 123", analysis)

    listing = store.list()

    assert listing.total == 1
    assert listing.items[0].analysis_id == analysis.analysis_id
    assert store.delete(analysis.analysis_id) is True
    assert store.get(analysis.analysis_id) is None
    assert store.delete(analysis.analysis_id) is False
    store.engine.dispose()


def test_history_api_lists_opens_and_deletes(isolated_history_store):
    analysis = _analysis()
    isolated_history_store.save("서울특별시 강서구 화곡로 123", analysis)

    listing = client.get("/api/v1/analysis-history")
    detail = client.get(f"/api/v1/analysis-history/{analysis.analysis_id}")
    deleted = client.delete(f"/api/v1/analysis-history/{analysis.analysis_id}")
    missing = client.get(f"/api/v1/analysis-history/{analysis.analysis_id}")

    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert detail.status_code == 200
    assert detail.json()["facts"]["owner"] is None
    assert deleted.status_code == 204
    assert missing.status_code == 404


def test_feedback_is_upserted_without_free_text_or_document_content(tmp_path):
    store = AnalysisHistoryStore(tmp_path / "history.db")
    analysis = _analysis()
    store.save("서울특별시 강서구 화곡로 123", analysis)

    first = store.save_feedback(
        analysis.analysis_id,
        AnalysisFeedbackCreate(target="mortgage_amount", verdict="correct"),
    )
    updated = store.save_feedback(
        analysis.analysis_id,
        AnalysisFeedbackCreate(
            target="mortgage_amount",
            verdict="incorrect",
            corrected_value=230_000_000,
        ),
    )
    listing = store.list_feedback(analysis.analysis_id)

    assert first is not None
    assert updated is not None
    assert updated.id == first.id
    assert updated.original_value == analysis.facts.mortgage_amount
    assert updated.corrected_value == 230_000_000
    assert listing is not None
    assert listing.total == 1
    with store.sessions() as session:
        assert session.query(AnalysisFeedbackRecord).count() == 1
    store.engine.dispose()


def test_feedback_api_validates_amount_and_is_deleted_with_history(
    isolated_history_store,
):
    analysis = _analysis()
    isolated_history_store.save("서울특별시 강서구 화곡로 123", analysis)

    invalid = client.post(
        f"/api/v1/analysis-history/{analysis.analysis_id}/feedback",
        json={"target": "deposit", "verdict": "incorrect"},
    )
    saved = client.post(
        f"/api/v1/analysis-history/{analysis.analysis_id}/feedback",
        json={
            "target": "deposit",
            "verdict": "incorrect",
            "corrected_value": 140_000_000,
        },
    )
    listing = client.get(
        f"/api/v1/analysis-history/{analysis.analysis_id}/feedback"
    )
    deleted = client.delete(f"/api/v1/analysis-history/{analysis.analysis_id}")

    assert invalid.status_code == 422
    assert saved.status_code == 200
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert deleted.status_code == 204
    with isolated_history_store.sessions() as session:
        assert session.query(AnalysisFeedbackRecord).count() == 0


def test_feedback_api_rejects_unknown_analysis(isolated_history_store):
    response = client.post(
        "/api/v1/analysis-history/missing/feedback",
        json={"target": "overall", "verdict": "correct"},
    )

    assert response.status_code == 404
