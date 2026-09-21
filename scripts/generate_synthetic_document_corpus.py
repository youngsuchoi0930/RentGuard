"""Generate a deterministic, privacy-safe PDF regression corpus.

The corpus is stored as one PDF so it is easy to move between development
machines. Every case occupies three consecutive pages: registry, building
ledger, and lease contract. The companion manifest is the hand-authored
ground truth used by ``evaluate_synthetic_document_corpus.py``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf" / "rentguard-synthetic-corpus"
PDF_PATH = OUTPUT_DIR / "rentguard-synthetic-corpus-30.pdf"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"
PAGE_WIDTH, PAGE_HEIGHT = A4


def _font_path(*candidates: str) -> Path:
    path = next((Path(value) for value in candidates if Path(value).exists()), None)
    if path is None:
        raise FileNotFoundError(
            "A Korean TrueType font is required. Install Malgun Gothic on "
            "Windows or the fonts-nanum package on Linux."
        )
    return path


FONT_REGULAR = _font_path(
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
)
FONT_BOLD = _font_path(
    "C:/Windows/Fonts/malgunbd.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
)

pdfmetrics.registerFont(TTFont("Malgun", str(FONT_REGULAR)))
pdfmetrics.registerFont(TTFont("Malgun-Bold", str(FONT_BOLD)))


@dataclass(frozen=True)
class SyntheticCase:
    case_id: str
    profile: str
    district: str
    dong: str
    road: str
    building_number: int
    lot_number: str
    unit: str
    building_name: str
    owner: str
    landlord: str
    tenant: str
    input_deposit: int
    contract_deposit: int
    input_monthly_rent: int
    contract_monthly_rent: int
    mortgage_amounts: tuple[int, ...]
    active_rights: tuple[str, ...]
    cancelled_mortgage: bool
    is_illegal_building: bool
    contract_address_override: str | None = None

    @property
    def road_address(self) -> str:
        return (
            f"서울특별시 {self.district} {self.road} "
            f"{self.building_number}, {self.unit}"
        )

    @property
    def lot_address(self) -> str:
        return (
            f"[집합건물] 서울특별시 {self.district} {self.dong} "
            f"{self.lot_number} 제{int(self.unit[:-1]) // 100}층 제{self.unit}"
        )

    @property
    def contract_address(self) -> str:
        return self.contract_address_override or self.road_address


PROFILES = (
    ["normal"] * 5
    + ["low_mortgage"] * 4
    + ["high_mortgage"] * 4
    + ["multiple_mortgage"] * 2
    + ["owner_mismatch"] * 2
    + ["address_mismatch"] * 2
    + ["deposit_mismatch"] * 2
    + ["rent_mismatch"]
    + ["illegal_building"] * 2
    + ["seizure", "provisional_seizure", "trust", "auction"]
    + ["cancelled_mortgage", "mixed_high"]
)

LOCATIONS = (
    ("강서구", "화곡동", "합성로"),
    ("마포구", "망원동", "검증로"),
    ("관악구", "봉천동", "안심길"),
    ("광진구", "중곡동", "샘플로"),
    ("은평구", "응암동", "테스트로"),
    ("송파구", "잠실동", "안전로"),
)

OWNERS = (
    "김하늘", "이새봄", "박윤슬", "최가을", "정겨울",
    "강한결", "조하람", "윤다온", "장나래", "임다운",
)

TENANTS = (
    "한지우", "오해솔", "서라온", "신바다", "권여울",
    "황다정", "안아람", "송이든", "류은채", "문다솜",
)

RIGHT_LABELS = {
    "seizure": "압류",
    "provisional_seizure": "가압류",
    "trust": "신탁등기",
    "auction": "강제경매개시결정",
}


def _cases() -> list[SyntheticCase]:
    cases: list[SyntheticCase] = []
    for index, profile in enumerate(PROFILES, start=1):
        district, dong, road = LOCATIONS[(index - 1) % len(LOCATIONS)]
        owner = OWNERS[(index - 1) % len(OWNERS)]
        landlord = owner
        tenant = TENANTS[(index - 1) % len(TENANTS)]
        deposit = 30_000_000 + ((index - 1) % 8) * 10_000_000
        rent = 400_000 + ((index - 1) % 6) * 100_000
        contract_deposit = deposit
        contract_rent = rent
        mortgages: tuple[int, ...] = ()
        rights: tuple[str, ...] = ()
        cancelled_mortgage = False
        illegal = False

        if profile == "low_mortgage":
            mortgages = (40_000_000 + (index % 3) * 10_000_000,)
        elif profile == "high_mortgage":
            mortgages = (180_000_000 + (index % 3) * 20_000_000,)
        elif profile == "multiple_mortgage":
            mortgages = (70_000_000, 90_000_000)
        elif profile == "owner_mismatch":
            landlord = OWNERS[index % len(OWNERS)]
        elif profile == "deposit_mismatch":
            contract_deposit = deposit + 10_000_000
        elif profile == "rent_mismatch":
            contract_rent = rent + 100_000
        elif profile == "illegal_building":
            illegal = True
        elif profile in RIGHT_LABELS:
            rights = (profile,)
        elif profile == "cancelled_mortgage":
            mortgages = (120_000_000,)
            cancelled_mortgage = True
        elif profile == "mixed_high":
            mortgages = (220_000_000,)
            rights = ("seizure",)
            illegal = True
            landlord = OWNERS[index % len(OWNERS)]

        unit = f"{200 + index}호"
        building_number = 100 + index
        contract_override = None
        if profile == "address_mismatch":
            contract_override = (
                f"서울특별시 {district} {road} "
                f"{building_number + 900}, {unit}"
            )
        cases.append(SyntheticCase(
            case_id=f"RG-SYN-{index:03d}",
            profile=profile,
            district=district,
            dong=dong,
            road=road,
            building_number=building_number,
            lot_number=f"{100 + index}-{(index % 9) + 1}",
            unit=unit,
            building_name=f"렌트가드 합성주택 {index:02d}",
            owner=owner,
            landlord=landlord,
            tenant=tenant,
            input_deposit=deposit,
            contract_deposit=contract_deposit,
            input_monthly_rent=rent,
            contract_monthly_rent=contract_rent,
            mortgage_amounts=mortgages,
            active_rights=rights,
            cancelled_mortgage=cancelled_mortgage,
            is_illegal_building=illegal,
            contract_address_override=contract_override,
        ))
    return cases


def _page_header(pdf: canvas.Canvas, title: str, subtitle: str, case: SyntheticCase) -> float:
    pdf.setFillColor(colors.HexColor("#F7F9FC"))
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    pdf.saveState()
    pdf.setFont("Malgun-Bold", 30)
    pdf.setFillColor(colors.Color(0.83, 0.10, 0.10, alpha=0.09))
    pdf.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
    pdf.rotate(32)
    pdf.drawCentredString(0, 0, "합성 테스트 전용 · 법적 효력 없음")
    pdf.restoreState()
    pdf.setFillColor(colors.HexColor("#17335F"))
    pdf.setFont("Malgun-Bold", 20)
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 24 * mm, title)
    pdf.setFont("Malgun", 8.5)
    pdf.setFillColor(colors.HexColor("#627086"))
    pdf.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 31 * mm, subtitle)
    pdf.setFillColor(colors.HexColor("#E7EEF7"))
    pdf.roundRect(18 * mm, PAGE_HEIGHT - 46 * mm, PAGE_WIDTH - 36 * mm, 9 * mm, 3 * mm, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#17335F"))
    pdf.setFont("Malgun-Bold", 8)
    pdf.drawString(22 * mm, PAGE_HEIGHT - 42.5 * mm, f"케이스 {case.case_id}")
    pdf.drawRightString(PAGE_WIDTH - 22 * mm, PAGE_HEIGHT - 42.5 * mm, f"시나리오 {case.profile}")
    return PAGE_HEIGHT - 55 * mm


def _section(pdf: canvas.Canvas, y: float, title: str) -> float:
    pdf.setFillColor(colors.HexColor("#17335F"))
    pdf.setFont("Malgun-Bold", 10.5)
    pdf.drawString(18 * mm, y, title)
    pdf.setStrokeColor(colors.HexColor("#C7D2E2"))
    pdf.line(18 * mm, y - 2.3 * mm, PAGE_WIDTH - 18 * mm, y - 2.3 * mm)
    return y - 8 * mm


def _line(pdf: canvas.Canvas, y: float, text: str, *, bold: bool = False, indent: int = 0) -> float:
    pdf.setFont("Malgun-Bold" if bold else "Malgun", 8.4)
    pdf.setFillColor(colors.HexColor("#202A3B"))
    pdf.drawString((18 + indent) * mm, y, text)
    return y - 5.3 * mm


def _footer(pdf: canvas.Canvas, document_kind: str) -> None:
    pdf.setFont("Malgun", 7)
    pdf.setFillColor(colors.HexColor("#768296"))
    pdf.drawString(18 * mm, 11 * mm, "RentGuard synthetic regression corpus · 실제 인물·주소·관계와 무관")
    pdf.drawRightString(PAGE_WIDTH - 18 * mm, 11 * mm, document_kind)


def _registry_page(case: SyntheticCase) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    y = _page_header(pdf, "등기사항전부증명서", "(현재 유효사항) · 집합건물 · 합성문서", case)
    y = _line(pdf, y, case.lot_address)
    y = _line(pdf, y, "도로명주소", bold=True)
    y = _line(pdf, y, case.road_address)
    y = _line(pdf, y, "건물명칭", bold=True)
    y = _line(pdf, y, case.building_name)
    y = _line(pdf, y, "열람일시 2026년 9월 21일 10:30")
    y = _section(pdf, y - 2 * mm, "【 갑 구 】 소유권에 관한 사항")
    y = _line(pdf, y, "1")
    y = _line(pdf, y, "소유권보존")
    y = _line(pdf, y, "2020년 1월 15일 제10001호")
    y = _line(pdf, y, f"소유자 {case.owner}", bold=True)
    for rank, right in enumerate(case.active_rights, start=2):
        y = _line(pdf, y, str(rank))
        y = _line(pdf, y, RIGHT_LABELS[right], bold=True)
        y = _line(pdf, y, f"2025년 {rank}월 10일 제{21000 + rank}호")
    y = _section(pdf, y - 2 * mm, "【 을 구 】 소유권 이외의 권리에 관한 사항")
    if not case.mortgage_amounts:
        y = _line(pdf, y, "기록사항 없음")
    for rank, amount in enumerate(case.mortgage_amounts, start=1):
        y = _line(pdf, y, str(rank))
        y = _line(pdf, y, "근저당권설정", bold=True)
        y = _line(pdf, y, f"2024년 {rank + 2}월 12일 제{31000 + rank}호")
        y = _line(pdf, y, f"채권최고액 금{amount:,}원", bold=True)
        y = _line(pdf, y, f"채무자 {case.owner}")
        y = _line(pdf, y, f"근저당권자 합성은행 {rank}")
    if case.cancelled_mortgage:
        y = _line(pdf, y, "2")
        y = _line(pdf, y, "1번 근저당권설정등기 말소", bold=True)
        y = _line(pdf, y, "2026년 1월 7일 해지")
    _footer(pdf, "REGISTRY")
    pdf.save()
    return stream.getvalue()


def _ledger_page(case: SyntheticCase) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    y = _page_header(pdf, "일반건축물대장(갑)", "합성문서 · 발급번호 RG-SYNTHETIC", case)
    fields = (
        ("대지위치", f"서울특별시 {case.district} {case.dong}"),
        ("지번", case.lot_number),
        ("도로명주소", case.road_address),
        ("명칭", case.building_name),
        ("주용도", "다세대주택"),
        ("주구조", "철근콘크리트구조"),
        ("세대수", f"{6 + (int(case.case_id[-3:]) % 7)}세대"),
        ("사용승인일", f"{2010 + (int(case.case_id[-3:]) % 12)}. 06. 20."),
        ("위반건축물 여부", "위반건축물 해당" if case.is_illegal_building else "해당 없음"),
    )
    for label, value in fields:
        y = _line(pdf, y, label, bold=True)
        y = _line(pdf, y, value, indent=4)
    y = _section(pdf, y - 2 * mm, "층별 개요")
    y = _line(pdf, y, "1층 철근콘크리트구조 주차장 82.51㎡")
    y = _line(pdf, y, f"{int(case.unit[:-1]) // 100}층 철근콘크리트구조 다세대주택 42.18㎡")
    _footer(pdf, "BUILDING LEDGER")
    pdf.save()
    return stream.getvalue()


def _contract_page(case: SyntheticCase) -> bytes:
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, pageCompression=1)
    y = _page_header(pdf, "주택임대차계약서", "보증금 있는 월세 · 합성문서", case)
    y = _line(pdf, y, f"임대인 {case.landlord}과 임차인 {case.tenant}은 아래와 같이 임대차계약을 체결한다.")
    y = _section(pdf, y - 2 * mm, "1. 임차주택의 표시")
    y = _line(pdf, y, "소재지", bold=True)
    y = _line(pdf, y, case.contract_address, indent=4)
    y = _line(pdf, y, "건물", bold=True)
    y = _line(pdf, y, "철근콘크리트구조 다세대주택 전유면적 42.18㎡", indent=4)
    y = _line(pdf, y, "임차할 부분", bold=True)
    y = _line(pdf, y, f"제{int(case.unit[:-1]) // 100}층 제{case.unit} 전부", indent=4)
    y = _section(pdf, y - 2 * mm, "2. 계약 내용")
    y = _line(pdf, y, f"보증금 {case.contract_deposit:,}원", bold=True)
    y = _line(pdf, y, f"계약금 {case.contract_deposit // 10:,}원")
    y = _line(pdf, y, f"잔금 {case.contract_deposit - case.contract_deposit // 10:,}원")
    y = _line(pdf, y, f"차임 {case.contract_monthly_rent:,}원", bold=True)
    y = _line(pdf, y, "임대차 기간 2026년 10월 10일부터 2028년 10월 9일까지")
    y = _section(pdf, y - 2 * mm, "3. 특약사항")
    y = _line(pdf, y, "1. 임대인은 잔금 지급 직전 최신 등기부를 임차인과 함께 확인한다.")
    y = _line(pdf, y, "2. 임대인은 보증보험 가입에 필요한 서류 제출에 협조한다.")
    y = _section(pdf, y - 2 * mm, "4. 계약 당사자")
    y = _line(pdf, y, "임대인", bold=True)
    y = _line(pdf, y, case.landlord, indent=4)
    y = _line(pdf, y, "임차인", bold=True)
    y = _line(pdf, y, case.tenant, indent=4)
    y = _line(pdf, y, "작성일 2026년 9월 21일")
    _footer(pdf, "LEASE CONTRACT")
    pdf.save()
    return stream.getvalue()


def _expected(case: SyntheticCase, start_page: int) -> dict:
    active_mortgage = 0 if case.cancelled_mortgage else sum(case.mortgage_amounts)
    active_right_types = list(case.active_rights)
    if active_mortgage:
        active_right_types.insert(0, "mortgage")
    address_status = "mismatch" if case.contract_address_override else "verified"
    return {
        "case_id": case.case_id,
        "source_kind": "synthetic",
        "profile": case.profile,
        "pages": {
            "registry": start_page,
            "building_ledger": start_page + 1,
            "lease_contract": start_page + 2,
        },
        "input": {
            "address": case.road_address,
            "deposit": case.input_deposit,
            "monthly_rent": case.input_monthly_rent,
        },
        "expected": {
            "registry": {
                "owner": case.owner,
                "mortgage_amount": active_mortgage,
                "active_right_types": active_right_types,
            },
            "building_ledger": {
                "road_address": case.road_address,
                "main_use": "다세대주택",
                "is_illegal_building": case.is_illegal_building,
            },
            "lease_contract": {
                "landlord": case.landlord,
                "tenant": case.tenant,
                "address": case.contract_address,
                "deposit": case.contract_deposit,
                "monthly_rent": case.contract_monthly_rent,
            },
            "cross_checks": {
                "owner-landlord": "mismatch" if case.landlord != case.owner else "verified",
                "property-address": address_status,
                "deposit": "mismatch" if case.contract_deposit != case.input_deposit else "verified",
                "monthly-rent": "mismatch" if case.contract_monthly_rent != case.input_monthly_rent else "verified",
                "illegal-building": "mismatch" if case.is_illegal_building else "verified",
            },
        },
    }


def generate() -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    manifest_cases = []
    for index, case in enumerate(_cases()):
        page_number = index * 3 + 1
        manifest_cases.append(_expected(case, page_number))
        for payload in (_registry_page(case), _ledger_page(case), _contract_page(case)):
            source = PdfReader(BytesIO(payload))
            writer.add_page(source.pages[0])

    with PDF_PATH.open("wb") as handle:
        writer.write(handle)

    manifest = {
        "corpus_version": "1.0.0",
        "source_kind": "synthetic",
        "notice": (
            "All people, addresses, buildings, institutions, and contracts are "
            "fictional. This corpus is for regression testing only and must not "
            "be used as a real-world model evaluation set."
        ),
        "case_count": len(manifest_cases),
        "documents_per_case": 3,
        "page_count": len(manifest_cases) * 3,
        "pdf": PDF_PATH.name,
        "cases": manifest_cases,
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return PDF_PATH, MANIFEST_PATH


def main() -> None:
    pdf_path, manifest_path = generate()
    print(pdf_path)
    print(manifest_path)


if __name__ == "__main__":
    main()
