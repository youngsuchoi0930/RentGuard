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


def test_registry_extraction_endpoint_uses_uploaded_pdf():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    pdf = root / "output" / "pdf" / "rentguard-fixtures" / "registry_risky_digital.pdf"
    with pdf.open("rb") as stream:
        response = client.post(
            "/api/v1/documents/registry/extract",
            files={"file": (pdf.name, stream, "application/pdf")},
        )
    assert response.status_code == 200
    result = response.json()
    assert result["ownership"][0]["owner_name"] == "김민준"
    assert result["encumbrances"][0]["maximum_claim_amount"] == 110000000


def test_document_bundle_endpoint_extracts_and_cross_checks_all_pdfs():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    paths = {
        "registry": fixtures / "registry_risky_digital.pdf",
        "building_ledger": fixtures / "building_ledger_risky.pdf",
        "lease_contract": fixtures / "lease_contract_risky.pdf",
    }
    streams = {name: path.open("rb") for name, path in paths.items()}
    try:
        response = client.post(
            "/api/v1/document-bundles/extract",
            data={
                "address": "서울특별시 강서구 화곡로 123",
                "deposit": "150000000",
                "monthly_rent": "100000",
            },
            files={
                name: (paths[name].name, stream, "application/pdf")
                for name, stream in streams.items()
            },
        )
    finally:
        for stream in streams.values():
            stream.close()

    assert response.status_code == 200
    result = response.json()
    assert result["lease_contract"]["deposit"]["value"] == 150000000
    assert result["building_ledger"]["property"]["main_use"] == "다세대주택"
    assert all(check["status"] == "verified" for check in result["cross_checks"])
