from __future__ import annotations

import re

from ..building_schemas import BuildingLedgerExtraction, BuildingMetadata, BuildingProperty
from ..registry_schemas import ReviewItem, SourceEvidence
from .document_parser_utils import clean, compact, document_confidence, evidence, labeled_value, parse_date
from .pdf_extractor import ExtractedDocument, extract_pdf


def _ledger_type(text: str) -> str:
    value = compact(text)
    if "일반건축물대장" in value:
        return "general"
    if "집합건축물대장" in value and "전유부" in value:
        return "collective_unit"
    if "집합건축물대장" in value and "표제부" in value:
        return "collective_title"
    return "unknown"


def _illegal_status(raw: str | None) -> bool | None:
    if not raw:
        return None
    value = compact(raw)
    if any(token in value for token in ("해당없음", "미해당", "위반사항없음")):
        return False
    if any(token in value for token in ("위반건축물", "해당", "위반내용")):
        return True
    return None


def parse_building_ledger(document: ExtractedDocument) -> BuildingLedgerExtraction:
    text = clean(document.text)
    compact_text = compact(text)
    location = labeled_value(text, ("대지위치", "소재지"))
    lot_number = labeled_value(text, ("지번",))
    lot_address = " ".join(value for value in (location, lot_number) if value) or None
    road_address = labeled_value(text, ("도로명주소", "도로명 주소"))
    building_name = labeled_value(text, ("명칭", "건물명칭"))
    main_use = labeled_value(text, ("주용도", "주 용도"))
    structure = labeled_value(text, ("주구조", "주 구조"))
    households_raw = labeled_value(text, ("세대수", "세대 수"))
    households_match = re.search(r"(\d+)\s*세대", households_raw or "")
    approval_raw = labeled_value(text, ("사용승인일", "사용 승인일"))
    illegal_raw = labeled_value(text, ("위반건축물 여부", "위반건축물", "위반 여부"))
    illegal_status = _illegal_status(illegal_raw)

    evidence_map: dict[str, SourceEvidence] = {}
    for field, raw in (
        ("lot_address", lot_address),
        ("road_address", road_address),
        ("building_name", building_name),
        ("main_use", main_use),
        ("structure", structure),
        ("households", households_raw),
        ("approval_date", approval_raw),
        ("is_illegal_building", illegal_raw),
    ):
        if raw:
            evidence_map[field] = evidence(document, raw, "ledger_overview")

    needs_review: list[ReviewItem] = []
    if "건축물대장" not in compact_text:
        needs_review.append(ReviewItem(code="DOCUMENT_TYPE_MISMATCH", severity="blocking", message="건축물대장으로 확인되지 않는 문서입니다."))
    if not road_address and not lot_address:
        needs_review.append(ReviewItem(code="LEDGER_ADDRESS_NOT_FOUND", severity="blocking", message="건축물대장 주소를 추출하지 못했습니다."))
    if not main_use:
        needs_review.append(ReviewItem(code="BUILDING_USE_NOT_FOUND", severity="warning", message="건축물 주용도를 추출하지 못했습니다."))
    if illegal_status is None:
        needs_review.append(ReviewItem(code="ILLEGAL_STATUS_UNKNOWN", severity="blocking", message="위반건축물 여부를 확인하지 못했습니다."))

    warnings: list[str] = []
    if document.method == "ocr" and document_confidence(document) < .75:
        warnings.append("OCR 평균 신뢰도가 낮아 건축물대장 원문 확인이 필요합니다.")
    return BuildingLedgerExtraction(
        document=BuildingMetadata(ledger_type=_ledger_type(text), pages=len(document.pages)),
        property=BuildingProperty(
            lot_address=lot_address,
            road_address=road_address,
            building_name=building_name,
            main_use=main_use,
            structure=structure,
            households=int(households_match.group(1)) if households_match else None,
            approval_date=parse_date(approval_raw) if approval_raw else None,
            is_illegal_building=illegal_status,
        ),
        evidence=evidence_map,
        extraction_method=document.method,
        confidence=document_confidence(document),
        warnings=warnings,
        needs_review=needs_review,
    )


def extract_building_ledger(data: bytes, *, allow_ocr: bool = True) -> BuildingLedgerExtraction:
    return parse_building_ledger(extract_pdf(data, allow_ocr=allow_ocr))
