from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_endpoint_returns_explainable_result():
    response = client.post(
        "/api/v1/analyses",
        data={
            "address": "서울특별시 강서구 화곡로 123",
            "deposit": "150000000",
            "monthly_rent": "100000",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["score"] == 73
    assert result["grade"] == "높음"
    assert result["facts"]["deposit"] == 150000000
    assert len(result["actions"]) == 3
