from __future__ import annotations

import re

from ..lease_schemas import (
    ContractMetadata,
    ContractMoney,
    ContractParty,
    ContractProperty,
    LeaseContractExtraction,
    LeasePeriod,
    SpecialTerm,
)
from ..registry_schemas import ReviewItem
from .document_parser_utils import (
    DATE_RE,
    clean,
    compact,
    document_confidence,
    evidence,
    labeled_value,
    parse_date,
    parse_money,
)
from .pdf_extractor import ExtractedDocument, extract_pdf


def _money_field(document: ExtractedDocument, text: str, labels: tuple[str, ...]) -> ContractMoney:
    raw = None
    compact_labels = tuple(compact(label) for label in labels)
    # OCR commonly reads a populated table row as one line (for example,
    # "보증금150,000,000원") while also detecting an unrelated blank label cell
    # elsewhere in a multi-page form. Prefer an inline value that actually
    # contains a number before falling back to generic label-cell handling.
    for line in (line.strip() for line in text.splitlines() if line.strip()):
        line_compact = compact(line)
        for label in compact_labels:
            if not line_compact.startswith(label) or len(line_compact) == len(label):
                continue
            candidate = line_compact[len(label):]
            if parse_money(candidate) is not None:
                raw = candidate
                break
        if raw is not None:
            break
    if raw is None:
        raw = labeled_value(text, labels)
    return ContractMoney(
        value=parse_money(raw) if raw else None,
        evidence=evidence(document, raw, "contract_terms") if raw else None,
    )


def _parties(document: ExtractedDocument, text: str) -> list[ContractParty]:
    found: list[tuple[str, str, str]] = []
    intro = re.search(
        r"임대인\s*([가-힣A-Za-z·]{2,30})(?:과|와)\s*임차인\s*([가-힣A-Za-z·]{2,30})(?:은|는)",
        text,
    )
    if intro:
        found.extend([
            ("landlord", intro.group(1), intro.group(0)),
            ("tenant", intro.group(2), intro.group(0)),
        ])
    for role_ko, role in (("임대인", "landlord"), ("임차인", "tenant"), ("대리인", "agent")):
        if any(found_role == role for found_role, _, _ in found):
            continue
        match = re.search(rf"(?:^|\n){role_ko}\s*\n\s*([가-힣A-Za-z·]{{2,30}})(?:\n|$)", text)
        if match:
            found.append((role, match.group(1), match.group(0)))

    parties: list[ContractParty] = []
    seen: set[tuple[str, str]] = set()
    for role, name, raw in found:
        key = (role, name)
        if key in seen:
            continue
        seen.add(key)
        parties.append(ContractParty(
            role=role,
            name=name,
            evidence=evidence(document, raw, "contract_parties"),
        ))
    return parties


def _special_terms(document: ExtractedDocument, text: str) -> list[SpecialTerm]:
    match = re.search(r"(?:^|\n)3[.]?\s*특약사항\s*\n(?P<body>.*?)(?=\n4[.]?\s*계약\s*당사자|$)", text, re.DOTALL)
    if not match:
        return []
    lines = [line.strip() for line in match.group("body").splitlines() if line.strip()]
    terms: list[SpecialTerm] = []
    index = 0
    while index < len(lines):
        numbered = re.match(r"^(\d+)[.)]?\s*(.*)$", lines[index])
        if not numbered:
            index += 1
            continue
        order = int(numbered.group(1))
        content = numbered.group(2).strip()
        if not content and index + 1 < len(lines):
            index += 1
            content = lines[index]
        if content:
            terms.append(SpecialTerm(
                order=order,
                content=content,
                evidence=evidence(document, content, "contract_special_terms"),
            ))
        index += 1
    return terms


def _contract_type(text: str, deposit: int | None, monthly_rent: int | None) -> str:
    value = compact(text)
    if "전세" in value and not monthly_rent:
        return "jeonse"
    if deposit and monthly_rent:
        return "monthly_with_deposit"
    if monthly_rent:
        return "monthly"
    return "unknown"


def parse_lease_contract(document: ExtractedDocument) -> LeaseContractExtraction:
    text = clean(document.text)
    compact_text = compact(text)
    address = labeled_value(text, ("소재지", "임차주택의 소재지"))
    building = labeled_value(text, ("건물", "건물 표시"))
    leased_part = labeled_value(text, ("임차할 부분", "임차부분"))
    parties = _parties(document, text)
    deposit = _money_field(document, text, ("보증금",))
    contract_payment = _money_field(document, text, ("계약금",))
    balance = _money_field(document, text, ("잔금",))
    monthly_rent = _money_field(document, text, ("차임", "월세"))
    period_raw = labeled_value(text, ("임대차 기간", "임대차기간", "계약기간"))
    dates = list(DATE_RE.finditer(period_raw or ""))
    period = LeasePeriod(
        start=parse_date(dates[0].group(0)) if dates else None,
        end=parse_date(dates[1].group(0)) if len(dates) > 1 else None,
        evidence=evidence(document, period_raw, "contract_terms") if period_raw else None,
    )
    signed_raw = labeled_value(text, ("작성일", "계약일"))
    if not signed_raw:
        signed_match = re.search(r"작성일\s*[:：]?\s*([^\n]+)", text)
        signed_raw = signed_match.group(1) if signed_match else None

    needs_review: list[ReviewItem] = []
    if "임대차계약서" not in compact_text and not ("임대인" in compact_text and "임차인" in compact_text):
        needs_review.append(ReviewItem(code="DOCUMENT_TYPE_MISMATCH", severity="blocking", message="주택임대차계약서로 확인되지 않는 문서입니다."))
    if not address:
        needs_review.append(ReviewItem(code="CONTRACT_ADDRESS_NOT_FOUND", severity="blocking", message="계약 목적물 주소를 추출하지 못했습니다."))
    if not any(party.role == "landlord" for party in parties):
        needs_review.append(ReviewItem(code="LANDLORD_NOT_FOUND", severity="blocking", message="임대인 이름을 추출하지 못했습니다."))
    if deposit.value is None:
        needs_review.append(ReviewItem(code="DEPOSIT_NOT_FOUND", severity="blocking", message="보증금을 추출하지 못했습니다."))
    if not period.start or not period.end:
        needs_review.append(ReviewItem(code="LEASE_PERIOD_NOT_FOUND", severity="warning", message="임대차 기간을 완전히 추출하지 못했습니다."))

    warnings: list[str] = []
    if document.method == "ocr" and document_confidence(document) < .75:
        warnings.append("OCR 평균 신뢰도가 낮아 계약서 원문 확인이 필요합니다.")
    return LeaseContractExtraction(
        document=ContractMetadata(
            contract_type=_contract_type(text, deposit.value, monthly_rent.value),
            signed_at=parse_date(signed_raw) if signed_raw else None,
            pages=len(document.pages),
        ),
        property=ContractProperty(address=address, building_description=building, leased_part=leased_part),
        parties=parties,
        deposit=deposit,
        contract_payment=contract_payment,
        balance=balance,
        monthly_rent=monthly_rent,
        lease_period=period,
        special_terms=_special_terms(document, text),
        extraction_method=document.method,
        confidence=document_confidence(document),
        warnings=warnings,
        needs_review=needs_review,
    )


def extract_lease_contract(data: bytes, *, allow_ocr: bool = True) -> LeaseContractExtraction:
    return parse_lease_contract(extract_pdf(data, allow_ocr=allow_ocr))
