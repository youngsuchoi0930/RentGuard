from __future__ import annotations

import re
from datetime import datetime

from ..registry_schemas import (
    EncumbranceEntry,
    OwnershipEntry,
    RegistryExtraction,
    RegistryMetadata,
    RegistryProperty,
    ReviewItem,
    SourceEvidence,
)
from .pdf_extractor import ExtractedDocument, ExtractedPage, extract_pdf


SPACE_RE = re.compile(r"[ \t]+")
DATE_RE = re.compile(r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
AMOUNT_RE = re.compile(r"채권\s*최고액\s*(?:금)?\s*([0-9OIl,\. ]+)\s*원")


def _clean(text: str) -> str:
    return "\n".join(SPACE_RE.sub(" ", line).strip() for line in text.splitlines() if line.strip())


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return datetime(*(int(part) for part in match.groups())).date().isoformat()
    except ValueError:
        return None


def _money(value: str) -> int | None:
    normalized = value.translate(str.maketrans({"O": "0", "I": "1", "l": "1"}))
    digits = re.sub(r"[^0-9]", "", normalized)
    return int(digits) if digits else None


def _line_after(text: str, labels: tuple[str, ...]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact_labels = {_compact(label) for label in labels}
    for index, line in enumerate(lines[:-1]):
        if _compact(line) in compact_labels:
            return lines[index + 1]
    return None


def _address_candidates(text: str) -> tuple[str | None, str | None]:
    """Infer addresses from their contents when OCR changes the table reading order."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    address_lines = [
        line for line in lines
        if re.search(r"(?:특별시|광역시|특별자치시|특별자치도|도).*(?:시|군|구)", line)
        and re.search(r"\d", line)
    ]
    road = next(
        (line for line in address_lines if re.search(r"(?:대로|로|길)\s*\d", line)),
        None,
    )
    lot = next(
        (
            line for line in address_lines
            if line != road and re.search(r"(?:동|리|가)\s*\d+(?:-\d+)?", line)
        ),
        None,
    )
    return road, lot


def _page_for(pages: list[ExtractedPage], token: str) -> ExtractedPage:
    compact_token = _compact(token)
    return next((page for page in pages if compact_token in _compact(page.text)), pages[0])


def _evidence(document: ExtractedDocument, token: str, section: str, snippet: str) -> SourceEvidence:
    page = _page_for(document.pages, token)
    return SourceEvidence(
        page=page.number,
        section=section,
        raw_text=snippet.strip(),
        extraction_method=document.method,
        confidence=page.confidence,
    )


def _certificate_type(text: str) -> str:
    compact = _compact(text)
    if "말소사항포함" in compact:
        return "full_with_cancelled"
    if "현재유효사항" in compact and "전부" in compact:
        return "full_current"
    if "특정인지분" in compact:
        return "partial_specific_share"
    if "현재소유현황" in compact:
        return "partial_current_owners"
    if "지분취득이력" in compact:
        return "partial_share_history"
    return "unknown"


def _property_type(text: str) -> str:
    compact = _compact(text)
    if "집합건물" in compact or "전유부분" in compact:
        return "condominium"
    if "토지등기" in compact:
        return "land"
    if "건물등기" in compact or "건물의표시" in compact:
        return "building"
    return "unknown"


def _issued_at(text: str) -> str | None:
    compact = _compact(text)
    match = re.search(r"열람일시(20\d{2}년\d{1,2}월\d{1,2}일)(\d{1,2}:\d{2})?", compact)
    if not match:
        return None
    date = _date(match.group(1))
    return f"{date}T{match.group(2)}:00" if date and match.group(2) else date


def _extract_owners(document: ExtractedDocument, text: str) -> list[OwnershipEntry]:
    owners: list[OwnershipEntry] = []
    seen: set[str] = set()
    patterns = [
        re.compile(r"소유자\s*([가-힣]{2,10})"),
        re.compile(r"공유자\s*([가-힣]{2,10})"),
    ]
    for pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group(1)
            if name in seen:
                continue
            seen.add(name)
            snippet = match.group(0)
            owners.append(OwnershipEntry(
                owner_name=name,
                evidence=_evidence(document, snippet, "registry_a", snippet),
            ))
    return owners


def _extract_encumbrances(document: ExtractedDocument, text: str) -> list[EncumbranceEntry]:
    compact = _compact(text)
    entries: list[EncumbranceEntry] = []
    # PDF table extraction and OCR often emit a row's cells in different orders.
    # Pair fields inside a window centred on each mortgage row anchor instead of
    # assuming that every field follows "근저당권설정" in reading order.
    mortgage_matches = list(re.finditer(r"근저당권\s*설정", text))
    for index, match in enumerate(mortgage_matches):
        start = max(0, match.start() - 500)
        end = min(len(text), match.end() + 700)
        if index:
            previous = mortgage_matches[index - 1].start()
            start = max(start, (previous + match.start()) // 2)
        if index + 1 < len(mortgage_matches):
            following = mortgage_matches[index + 1].start()
            end = min(end, (match.start() + following) // 2)
        row = text[start:end]
        amount_match = AMOUNT_RE.search(row)
        holder_match = re.search(r"근저당권자\s*([^\n]+)", row)
        debtor_match = re.search(r"채무자\s*([^\n]+)", row)
        date_match = DATE_RE.search(row)
        snippet = row[:300]
        entries.append(EncumbranceEntry(
            right_type="mortgage",
            maximum_claim_amount=_money(amount_match.group(1)) if amount_match else None,
            holder=holder_match.group(1) if holder_match else None,
            debtor=debtor_match.group(1) if debtor_match else None,
            registered_at=_date(date_match.group(0)) if date_match else None,
            evidence=_evidence(document, "근저당권설정", "registry_b", snippet),
        ))

    keyword_types = [
        (r"가압류", "가압류", "provisional_seizure"),
        (r"(?<!가)압류", "압류", "seizure"),
        (r"신탁", "신탁", "trust"),
        (r"전세권", "전세권", "leasehold"),
    ]
    for pattern, keyword, right_type in keyword_types:
        if re.search(pattern, compact):
            entries.append(EncumbranceEntry(
                right_type=right_type,
                evidence=_evidence(document, keyword, "registry_a", keyword),
            ))
    return entries


def parse_registry(document: ExtractedDocument) -> RegistryExtraction:
    text = _clean(document.text)
    compact_text = _compact(text)
    certificate_type = _certificate_type(text)
    property_type = _property_type(text)
    ownership = _extract_owners(document, text)
    encumbrances = _extract_encumbrances(document, text)
    inferred_road, inferred_lot = _address_candidates(text)
    road_address = inferred_road or _line_after(text, ("도로명주소", "도로명 주소"))
    lot_address = inferred_lot or _line_after(text, ("소재지번", "소재 지번"))
    building_name = _line_after(text, ("건물명칭", "건물 명칭"))
    needs_review: list[ReviewItem] = []
    warnings: list[str] = []

    if not any(token in compact_text for token in ("등기사항전부증명서", "등기사항일부증명서", "소유권에관한사항")):
        needs_review.append(ReviewItem(
            code="DOCUMENT_TYPE_MISMATCH", severity="blocking",
            message="등기사항증명서로 확인되지 않는 문서입니다.",
        ))

    if certificate_type == "unknown":
        needs_review.append(ReviewItem(
            code="CERTIFICATE_TYPE_UNKNOWN", severity="warning",
            message="증명서 종류를 확인하지 못했습니다.",
        ))
    if certificate_type.startswith("partial_"):
        needs_review.append(ReviewItem(
            code="PARTIAL_CERTIFICATE", severity="blocking",
            message="일부증명서는 전체 권리관계 분석에 충분하지 않을 수 있습니다.",
        ))
    if not ownership:
        needs_review.append(ReviewItem(
            code="OWNER_NOT_FOUND", severity="blocking",
            message="현재 소유자를 자동 추출하지 못했습니다.",
        ))
    if not road_address and not lot_address:
        needs_review.append(ReviewItem(
            code="ADDRESS_NOT_FOUND", severity="blocking",
            message="부동산 주소를 자동 추출하지 못했습니다.",
        ))
    if any(
        entry.right_type == "mortgage" and entry.maximum_claim_amount is None
        for entry in encumbrances
    ):
        needs_review.append(ReviewItem(
            code="MORTGAGE_AMOUNT_NOT_FOUND", severity="blocking",
            message="근저당권은 찾았지만 채권최고액을 추출하지 못했습니다.",
        ))
    if document.method == "ocr" and document.pages and min(page.confidence for page in document.pages) < .75:
        warnings.append("OCR 평균 신뢰도가 낮아 원문 확인이 필요합니다.")

    confidences = [page.confidence for page in document.pages]
    confidence = sum(confidences) / len(confidences) if confidences else 0.0
    unit_match = re.search(r"(?:제)?(\d{2,5})호", road_address or building_name or "")
    return RegistryExtraction(
        document=RegistryMetadata(
            certificate_type=certificate_type,
            property_type=property_type,
            issued_at=_issued_at(text),
            pages=len(document.pages),
        ),
        property=RegistryProperty(
            lot_address=lot_address,
            road_address=road_address,
            building_name=building_name,
            unit=f"{unit_match.group(1)}호" if unit_match else None,
        ),
        ownership=ownership,
        encumbrances=encumbrances,
        extraction_method=document.method,
        confidence=confidence,
        warnings=warnings,
        needs_review=needs_review,
    )


def extract_registry(data: bytes, *, allow_ocr: bool = True) -> RegistryExtraction:
    return parse_registry(extract_pdf(data, allow_ocr=allow_ocr))
