from __future__ import annotations

import re
from datetime import datetime

from ..registry_schemas import SourceEvidence
from .pdf_extractor import ExtractedDocument, ExtractedPage


SPACE_RE = re.compile(r"[ \t]+")
DATE_RE = re.compile(r"(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})\s*(?:월|[.\-/])\s*(\d{1,2})\s*(?:일|[.]?)")


def clean(text: str) -> str:
    return "\n".join(SPACE_RE.sub(" ", line).strip() for line in text.splitlines() if line.strip())


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def parse_date(value: str) -> str | None:
    match = DATE_RE.search(value)
    if not match:
        return None
    try:
        return datetime(*(int(part) for part in match.groups())).date().isoformat()
    except ValueError:
        return None


def parse_money(value: str) -> int | None:
    normalized = value.translate(str.maketrans({"O": "0", "I": "1", "l": "1"}))
    candidates = re.findall(r"\d[\d, .]*", normalized)
    if not candidates:
        return None
    digits = re.sub(r"[^0-9]", "", max(candidates, key=len))
    return int(digits) if digits else None


def labeled_value(text: str, labels: tuple[str, ...]) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    compact_labels = {compact(label) for label in labels}
    compact_lines = [compact(line) for line in lines]
    # Prefer an exact label cell. A heading such as "보증금 있는 월세" must not
    # shadow the later table cell labelled simply "보증금".
    for index, line_compact in enumerate(compact_lines):
        if line_compact in compact_labels and index + 1 < len(lines):
            return lines[index + 1]
    for line_compact in compact_lines:
        for label in compact_labels:
            if line_compact.startswith(label) and len(line_compact) > len(label):
                return line_compact[len(label):]
    return None


def page_for(pages: list[ExtractedPage], token: str) -> ExtractedPage:
    compact_token = compact(token)
    return next((page for page in pages if compact_token in compact(page.text)), pages[0])


def evidence(document: ExtractedDocument, token: str, section: str) -> SourceEvidence:
    page = page_for(document.pages, token)
    return SourceEvidence(
        page=page.number,
        section=section,
        raw_text=token.strip(),
        extraction_method=document.method,
        confidence=page.confidence,
    )


def document_confidence(document: ExtractedDocument) -> float:
    confidences = [page.confidence for page in document.pages]
    return sum(confidences) / len(confidences) if confidences else 0.0
