from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis_endpoint_returns_explainable_result(monkeypatch):
    from pathlib import Path

    from app.schemas import AIExplanation

    async def fake_explanation(**_kwargs):
        return AIExplanation(
            status="generated",
            provider="gemini",
            model="gemini-3.5-flash-lite",
            overview="문서 분석 결과를 쉬운 말로 정리했습니다.",
            caution="확인이 필요한 권리관계가 있습니다.",
            limitation="시세 연동 전이라 최종 판단에는 한계가 있습니다.",
            privacy_note="개인정보를 전송하지 않았습니다.",
        )

    async def fake_public_data(_address):
        return None

    monkeypatch.setattr("app.main.generate_gemini_explanation", fake_explanation)
    monkeypatch.setattr("app.main.fetch_public_data", fake_public_data)

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
            "/api/v1/analyses",
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
    assert result["mode"] == "contract_review"
    assert result["status"] == "partial"
    assert result["score"] == 12
    assert result["grade"] == "주의"
    assert result["facts"]["owner"] == "김민준"
    assert result["facts"]["contract_owner"] == "김민준"
    assert result["facts"]["mortgage_amount"] == 110000000
    assert result["facts"]["deposit"] == 150000000
    assert result["facts"]["estimated_value"] is None
    assert result["market_data"]["status"] == "not_connected"
    assert result["ai_explanation"]["status"] == "generated"
    assert result["documents"]["lease_contract"]["deposit"]["value"] == 150000000
    assert all(
        check["status"] == "verified"
        for check in result["documents"]["cross_checks"]
    )
    assert len(result["actions"]) == 3


def test_contract_review_requires_all_three_documents():
    response = client.post(
        "/api/v1/analyses",
        data={
            "address": "서울특별시 강서구 화곡로 123",
            "deposit": "150000000",
            "monthly_rent": "100000",
        },
    )

    assert response.status_code == 422


def test_precheck_accepts_registry_and_building_ledger_without_contract(monkeypatch):
    from pathlib import Path

    from app.schemas import AIExplanation
    from app.services.public_data import MarketEstimate, OfficialBuilding, PublicDataResult

    async def fake_explanation(**_kwargs):
        return AIExplanation(
            status="disabled",
            provider="gemini",
            model="gemini-3.5-flash-lite",
            message="테스트에서는 생성하지 않습니다.",
        )

    async def fake_public_data(_address):
        return PublicDataResult(
            address=None,
            building=OfficialBuilding(status="unavailable", message="테스트"),
            market=MarketEstimate(
                status="available",
                estimated_value=210_000_000,
                estimated_value_low=205_000_000,
                estimated_value_high=215_000_000,
                transaction_count=10,
                volatility=.02,
                message="테스트 실거래 10건",
            ),
        )

    monkeypatch.setattr("app.main.generate_gemini_explanation", fake_explanation)
    monkeypatch.setattr("app.main.fetch_public_data", fake_public_data)

    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    paths = {
        "registry": fixtures / "registry_risky_digital.pdf",
        "building_ledger": fixtures / "building_ledger_risky.pdf",
    }
    streams = {name: path.open("rb") for name, path in paths.items()}
    try:
        response = client.post(
            "/api/v1/analyses",
            data={
                "analysis_mode": "precheck",
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
    assert result["mode"] == "precheck"
    assert result["documents"]["lease_contract"] is None
    assert result["facts"]["contract_owner"] is None
    assert result["facts"]["estimated_value_low"] == 205_000_000
    assert result["facts"]["estimated_value_high"] == 215_000_000
    assert result["grade"] == "주의"
    assert all("계약서" not in check["label"] for check in result["documents"]["cross_checks"])


def test_reviewed_extractions_apply_corrections_and_keep_page_evidence(monkeypatch):
    from pathlib import Path

    from app.schemas import AIExplanation

    async def fake_explanation(**_kwargs):
        return AIExplanation(
            status="disabled",
            provider="gemini",
            model="gemini-3.5-flash-lite",
            message="테스트에서는 생성하지 않습니다.",
        )

    async def fake_public_data(_address):
        return None

    monkeypatch.setattr("app.main.generate_gemini_explanation", fake_explanation)
    monkeypatch.setattr("app.main.fetch_public_data", fake_public_data)

    root = Path(__file__).resolve().parents[3]
    fixtures = root / "output" / "pdf" / "rentguard-fixtures"
    registry_path = fixtures / "registry_risky_digital.pdf"
    ledger_path = fixtures / "building_ledger_risky.pdf"
    with registry_path.open("rb") as registry, ledger_path.open("rb") as ledger:
        extraction_response = client.post(
            "/api/v1/document-bundles/extract",
            data={
                "analysis_mode": "precheck",
                "address": "서울특별시 강서구 화곡로 123",
                "deposit": "30000000",
                "monthly_rent": "1300000",
            },
            files={
                "registry": (registry_path.name, registry, "application/pdf"),
                "building_ledger": (ledger_path.name, ledger, "application/pdf"),
            },
        )
    assert extraction_response.status_code == 200
    documents = extraction_response.json()
    documents["registry"]["ownership"][0]["owner_name"] = "수정소유자"

    response = client.post(
        "/api/v1/analyses/from-extractions",
        json={
            "mode": "precheck",
            "address": "서울특별시 강서구 화곡로 123",
            "deposit": 30000000,
            "monthly_rent": 1300000,
            "documents": documents,
            "corrections": [{
                "field": "registry.ownership.0.owner_name",
                "label": "등기 소유자",
                "previous_value": "김민준",
                "corrected_value": "수정소유자",
            }],
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["facts"]["owner"] == "수정소유자"
    assert result["corrections"][0]["field"] == "registry.ownership.0.owner_name"
    mortgage_signal = next(signal for signal in result["signals"] if signal["id"] == "mortgage-present")
    assert mortgage_signal["sources"][0]["page"] >= 1
    assert mortgage_signal["sources"][0]["raw_text"]
    owner_check = next(check for check in result["checks"] if check["label"] == "등기 소유자 확인")
    assert owner_check["sources"][0]["corrected"] is True
    assert owner_check["sources"][0]["corrected_value"] == "수정소유자"
    address_check = next(check for check in result["checks"] if check["label"] == "입력 주소와 두 문서")
    assert len(address_check["sources"]) >= 2


def test_address_search_endpoint_returns_safe_public_fields(monkeypatch):
    from app.schemas import AddressSuggestion

    async def fake_search(_keyword, *, limit):
        assert limit == 10
        return [
            AddressSuggestion(
                road_address="서울특별시 중구 세종대로 110",
                jibun_address="서울특별시 중구 태평로1가 31",
                zip_code="04524",
                building_name="서울특별시청",
            )
        ]

    monkeypatch.setattr("app.main.search_addresses", fake_search)
    response = client.get("/api/v1/addresses/search", params={"keyword": "세종대로 110"})

    assert response.status_code == 200
    assert response.json()["items"][0]["zip_code"] == "04524"


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
