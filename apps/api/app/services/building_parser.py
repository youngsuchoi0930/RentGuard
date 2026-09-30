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


def _identity_and_unit(text: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    building_name = None
    unit = None
    for index, line in enumerate(lines):
        if compact(line) != "호명칭":
            continue
        nearby = lines[index + 1:index + 5]
        for value in nearby:
            if unit is None and re.fullmatch(r"\d{1,5}\s*호", value):
                unit = compact(value)
            elif unit is None and building_name is not None and re.fullmatch(r"\d{1,5}", value):
                unit = f"{value}호"
            elif building_name is None and compact(value) not in {"호명칭", "대지위치", "지번"}:
                building_name = value
        break
    return building_name, unit


def _exclusive_section(text: str) -> tuple[str | None, int | None, str | None, float | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    start = next((index for index, line in enumerate(lines) if compact(line) == "전유부분"), 0)
    section = lines[start:start + 55]
    use_pattern = re.compile(r"(?:다세대주택|연립주택|공동주택|단독주택|다가구주택|아파트|오피스텔)")
    structure_pattern = re.compile(r"(?:콘크리트|철골|벽돌|블록|목조)")
    main_use = next((line for line in section if use_pattern.search(line)), None)
    structure = next((line for line in section if structure_pattern.search(line)), None)
    floor_value = next(
        (
            int(match.group(1))
            for line in section
            if (match := re.fullmatch(r"(?:지하|지)?(\d+)층", compact(line)))
        ),
        None,
    )
    area = None
    if main_use and main_use in section:
        use_index = section.index(main_use)
        for line in section[use_index + 1:use_index + 6]:
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3})?", compact(line)):
                candidate = float(compact(line))
                if 5 <= candidate <= 500:
                    area = candidate
                    break
    return main_use, floor_value, structure, area


USE_VALUE_RE = re.compile(
    r"^(?:단독주택(?:\(다가구주택\))?|다가구주택|다세대주택|"
    r"연립주택|공동주택|아파트|오피스텔|근린생활시설)$"
)
STRUCTURE_VALUE_RE = re.compile(
    r"^(?:철근콘크리트|철골철근콘크리트|철골|벽돌|블록|목)(?:구조|조)$"
)


def _content_line(text: str, pattern: re.Pattern[str]) -> str | None:
    candidates = [
        line.strip()
        for line in text.splitlines()
        if pattern.fullmatch(compact(line))
    ]
    return max(candidates, key=lambda value: len(compact(value)), default=None)


def _general_building_name(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rejected = {
        "명칭", "호수/가구수/세대수", "대지위치", "지번", "도로명주소",
    }
    for index, line in enumerate(lines):
        if compact(line) != "명칭":
            continue
        for candidate in lines[index + 1:index + 8]:
            value = compact(candidate)
            if value in rejected or not re.search(r"[가-힣A-Za-z]{2,}", value):
                continue
            if re.search(r"(?:특별시|광역시|시|군|구).*(?:동|리|가)$", value):
                continue
            if re.fullmatch(r"\d+호/\d+가구/\d+세대", value):
                continue
            return candidate
    inline = next(
        (
            re.sub(r"^\s*명칭\s*", "", line).strip()
            for line in lines
            if compact(line).startswith("명칭") and compact(line) != "명칭"
        ),
        None,
    )
    if inline and compact(inline).endswith("다가구"):
        inline = f"{inline}주택"
    return inline


def _general_lot_address(text: str) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    location_index = next(
        (
            index for index, line in enumerate(lines)
            if re.search(r"(?:특별시|광역시|특별자치|도).*(?:동|리|가)$", compact(line))
            and not re.search(r"(?:대로|로|길)\d", compact(line))
        ),
        None,
    )
    if location_index is None:
        return None
    lot_number = next(
        (
            compact(line)
            for line in lines[location_index + 1:location_index + 8]
            if re.fullmatch(r"\d+(?:-\d+)?", compact(line))
        ),
        None,
    )
    return " ".join(value for value in (lines[location_index], lot_number) if value)


def _approval_value(text: str, raw: str | None) -> str | None:
    if raw and parse_date(raw):
        return raw
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if compact(line) != "사용승인일":
            continue
        return next(
            (candidate for candidate in lines[index + 1:index + 25] if parse_date(candidate)),
            None,
        )
    return None


def parse_building_ledger(document: ExtractedDocument) -> BuildingLedgerExtraction:
    text = clean(document.text)
    compact_text = compact(text)
    ledger_type = _ledger_type(text)
    location = labeled_value(text, ("대지위치", "소재지"))
    lot_number = labeled_value(text, ("지번",))
    lot_address = " ".join(value for value in (location, lot_number) if value) or None
    if ledger_type == "general":
        inferred_lot_address = _general_lot_address(text)
        if inferred_lot_address:
            lot_address = inferred_lot_address
    road_address = labeled_value(text, ("도로명주소", "도로명 주소"))
    building_name = labeled_value(text, ("명칭", "건물명칭"))
    inferred_name, unit = _identity_and_unit(text)
    if ledger_type == "general":
        building_name = _general_building_name(text) or building_name
        unit = None
    elif (
        not building_name
        or compact(building_name) in {"호명칭", "명칭"}
        or not re.search(r"[가-힣A-Za-z]", building_name)
    ):
        building_name = inferred_name
    main_use = labeled_value(text, ("주용도", "주 용도"))
    structure = labeled_value(text, ("주구조", "주 구조"))
    inferred_use, floor, inferred_structure, exclusive_area = _exclusive_section(text)
    content_use = _content_line(text, USE_VALUE_RE)
    content_structure = _content_line(text, STRUCTURE_VALUE_RE)
    if not main_use or not USE_VALUE_RE.fullmatch(compact(main_use)):
        main_use = content_use or inferred_use
    if not structure or not STRUCTURE_VALUE_RE.fullmatch(compact(structure)):
        structure = content_structure or inferred_structure
    if ledger_type == "general":
        floor = None
        exclusive_area = None
    households_raw = labeled_value(text, ("세대수", "세대 수"))
    households_match = re.search(r"(\d+)\s*세대", households_raw or "")
    count_match = re.search(r"(\d+)호/(\d+)가구/(\d+)세대", compact_text)
    households = int(households_match.group(1)) if households_match else None
    if count_match:
        units, households_count, families = (int(value) for value in count_match.groups())
        households = households_count or families or units
    approval_raw = labeled_value(text, ("사용승인일", "사용 승인일"))
    approval_raw = _approval_value(text, approval_raw)
    illegal_raw = labeled_value(text, ("위반건축물 여부", "위반건축물", "위반 여부"))
    illegal_status = _illegal_status(illegal_raw)
    if illegal_status is None and "위반건축물" in compact_text:
        illegal_status = True
    elif (
        illegal_status is None
        and ledger_type == "general"
        and document_confidence(document) >= .85
    ):
        illegal_status = False

    evidence_map: dict[str, SourceEvidence] = {}
    for field, raw in (
        ("lot_address", lot_address),
        ("road_address", road_address),
        ("building_name", building_name),
        ("unit", unit),
        ("exclusive_area", str(exclusive_area) if exclusive_area is not None else None),
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
        document=BuildingMetadata(ledger_type=ledger_type, pages=len(document.pages)),
        property=BuildingProperty(
            lot_address=lot_address,
            road_address=road_address,
            building_name=building_name,
            unit=unit,
            floor=floor,
            exclusive_area=exclusive_area,
            main_use=main_use,
            structure=structure,
            households=households,
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
