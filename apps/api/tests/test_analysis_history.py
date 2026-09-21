import sqlite3
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


def test_feedback_overview_returns_statistics_and_masked_context(
    isolated_history_store,
):
    first_analysis = _analysis()
    isolated_history_store.save(
        "서울특별시 강서구 화곡로 123, 301호",
        first_analysis,
    )
    isolated_history_store.save_feedback(
        first_analysis.analysis_id,
        AnalysisFeedbackCreate(target="overall", verdict="correct"),
    )
    isolated_history_store.save_feedback(
        first_analysis.analysis_id,
        AnalysisFeedbackCreate(target="risk_signals", verdict="missing"),
    )

    response = client.get("/api/v1/feedback")
    filtered = client.get("/api/v1/feedback?verdict=missing")

    assert response.status_code == 200
    payload = response.json()
    assert payload["statistics"] == {
        "total": 2,
        "correct": 1,
        "incorrect": 0,
        "missing": 1,
        "analyses_with_feedback": 1,
        "positive_rate": 50.0,
        "pending": 2,
        "approved": 0,
        "excluded": 0,
    }
    assert payload["items"][0]["masked_address"] == (
        "서울특별시 강서구 · 상세주소 비공개"
    )
    assert "화곡로" not in response.text
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["verdict"] == "missing"


def test_initialize_migrates_existing_feedback_table(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE analysis_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id VARCHAR(36) NOT NULL,
            target VARCHAR(32) NOT NULL,
            verdict VARCHAR(16) NOT NULL,
            original_value INTEGER,
            corrected_value INTEGER,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO analysis_feedback (
            analysis_id, target, verdict, original_value, corrected_value,
            created_at, updated_at
        ) VALUES ('legacy-analysis', 'deposit', 'correct', 30000000, NULL,
                  '2026-09-15 00:00:00', '2026-09-15 00:00:00')
        """
    )
    connection.commit()
    connection.close()

    store = AnalysisHistoryStore(database_path)
    store.initialize()

    with store.sessions() as session:
        feedback = session.get(AnalysisFeedbackRecord, 1)
        assert feedback is not None
        assert feedback.review_status == "pending"
        assert feedback.reviewed_at is None
    store.engine.dispose()


def test_review_and_export_only_approved_feedback(isolated_history_store):
    analysis = _analysis()
    isolated_history_store.save(
        "서울특별시 강서구 화곡로 123, 301호",
        analysis,
    )
    first = isolated_history_store.save_feedback(
        analysis.analysis_id,
        AnalysisFeedbackCreate(target="deposit", verdict="correct"),
    )
    second = isolated_history_store.save_feedback(
        analysis.analysis_id,
        AnalysisFeedbackCreate(target="risk_signals", verdict="missing"),
    )
    assert first is not None
    assert second is not None

    approved = client.patch(
        f"/api/v1/feedback/{first.id}/review",
        json={"review_status": "approved"},
    )
    overview = client.get("/api/v1/feedback?review_status=approved")
    csv_export = client.get("/api/v1/feedback/export?format=csv")
    json_export = client.get("/api/v1/feedback/export?format=json")

    assert approved.status_code == 200
    assert approved.json()["review_status"] == "approved"
    assert approved.json()["reviewed_at"] is not None
    assert overview.status_code == 200
    assert overview.json()["total"] == 1
    assert overview.json()["statistics"]["pending"] == 1
    assert overview.json()["statistics"]["approved"] == 1
    assert csv_export.status_code == 200
    assert "verified_value" in csv_export.text
    assert str(first.id) in csv_export.text
    assert len(csv_export.text.strip().splitlines()) == 2
    assert "화곡로" not in csv_export.text
    assert json_export.status_code == 200
    assert len(json_export.json()) == 1
    assert json_export.json()[0]["feedback_id"] == first.id


def test_editing_feedback_resets_review_to_pending(isolated_history_store):
    analysis = _analysis()
    isolated_history_store.save("서울특별시 강서구 화곡로 123", analysis)
    feedback = isolated_history_store.save_feedback(
        analysis.analysis_id,
        AnalysisFeedbackCreate(target="overall", verdict="correct"),
    )
    assert feedback is not None
    reviewed = client.patch(
        f"/api/v1/feedback/{feedback.id}/review",
        json={"review_status": "approved"},
    )
    changed = client.post(
        f"/api/v1/analysis-history/{analysis.analysis_id}/feedback",
        json={"target": "overall", "verdict": "incorrect"},
    )

    assert reviewed.status_code == 200
    assert changed.status_code == 200
    assert changed.json()["review_status"] == "pending"
    assert changed.json()["reviewed_at"] is None
