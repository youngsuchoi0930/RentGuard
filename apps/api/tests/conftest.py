import pytest

from app.services.analysis_history import AnalysisHistoryStore


@pytest.fixture(autouse=True)
def isolated_history_store(tmp_path, monkeypatch):
    store = AnalysisHistoryStore(tmp_path / "rentguard-test.db")
    monkeypatch.setattr("app.main.get_history_store", lambda *_args, **_kwargs: store)
    yield store
    store.engine.dispose()
