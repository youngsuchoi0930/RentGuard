"""Generate privacy-safe PDF fixtures for the RentGuard document pipeline.

The documents are synthetic and visibly watermarked. They mimic the information
hierarchy that the extractor must handle without copying a real person's record.
"""

from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf" / "rentguard-fixtures"
TMP_DIR = ROOT / "tmp" / "pdfs"
FONT_REGULAR = Path("C:/Windows/Fonts/malgun.ttf")
FONT_BOLD = Path("C:/Windows/Fonts/malgunbd.ttf")
PAGE_W, PAGE_H = A4

pdfmetrics.registerFont(TTFont("Malgun", str(FONT_REGULAR)))
pdfmetrics.registerFont(TTFont("Malgun-Bold", str(FONT_BOLD)))


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleKo", parent=base["Title"], fontName="Malgun-Bold",
            fontSize=19, leading=25, alignment=TA_CENTER, spaceAfter=7 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleKo", parent=base["Normal"], fontName="Malgun",
            fontSize=8.5, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#596273"),
        ),
        "section": ParagraphStyle(
            "SectionKo", parent=base["Heading2"], fontName="Malgun-Bold",
            fontSize=11, leading=15, textColor=colors.HexColor("#17335F"), spaceBefore=4 * mm, spaceAfter=2 * mm,
        ),
        "body": ParagraphStyle(
            "BodyKo", parent=base["BodyText"], fontName="Malgun",
            fontSize=8.5, leading=13, textColor=colors.HexColor("#202A3B"),
        ),
        "small": ParagraphStyle(
            "SmallKo", parent=base["BodyText"], fontName="Malgun",
            fontSize=7, leading=10, textColor=colors.HexColor("#6E7889"),
        ),
    }


STYLES = styles()


def p(text: str, style: str = "body") -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), STYLES[style])


def watermark(canvas, _doc):
    canvas.saveState()
    canvas.setFont("Malgun-Bold", 36)
    canvas.setFillColor(colors.Color(0.82, 0.15, 0.15, alpha=0.10))
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(34)
    canvas.drawCentredString(0, 0, "테스트 전용 · 법적 효력 없음")
    canvas.restoreState()
    canvas.saveState()
    canvas.setFont("Malgun", 7)
    canvas.setFillColor(colors.HexColor("#7B8493"))
    canvas.drawString(18 * mm, 10 * mm, "RentGuard AI synthetic fixture")
    canvas.drawRightString(PAGE_W - 18 * mm, 10 * mm, f"PAGE {canvas.getPageNumber()}")
    canvas.restoreState()


def document(path: Path, story: list):
    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=16 * mm, bottomMargin=17 * mm,
        title=path.stem,
        author="RentGuard AI",
    )
    doc.build(story, onFirstPage=watermark, onLaterPages=watermark)


def styled_table(data, widths, header_rows=0, font_size=7.8):
    table = Table(data, colWidths=widths, repeatRows=header_rows)
    rules = [
        ("FONT", (0, 0), (-1, -1), "Malgun", font_size),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#677386")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header_rows:
        rules += [
            ("BACKGROUND", (0, 0), (-1, header_rows - 1), colors.HexColor("#EAF0F7")),
            ("FONT", (0, 0), (-1, header_rows - 1), "Malgun-Bold", font_size),
        ]
    table.setStyle(TableStyle(rules))
    return table


def make_registry(path: Path):
    story = [
        p("등기사항전부증명서", "title"),
        p("(말소사항 포함) · 집합건물 · 테스트 전용 합성문서", "subtitle"),
        Spacer(1, 5 * mm),
        styled_table([
            [p("고유번호", "small"), p("1144-2026-000042", "body"), p("열람일시", "small"), p("2026년 9월 7일 10:30", "body")],
            [p("소재지번", "small"), p("서울특별시 강서구 화곡동 123-45", "body"), p("건물명칭", "small"), p("렌트가드빌 301호", "body")],
            [p("도로명주소", "small"), p("서울특별시 강서구 화곡로 123, 301호", "body"), p("전유부분", "small"), p("철근콘크리트구조 42.18㎡", "body")],
        ], [26 * mm, 68 * mm, 26 * mm, 56 * mm]),
        p("【 표제부 】 건물의 표시", "section"),
        styled_table([
            [p("순위번호", "small"), p("접수", "small"), p("소재지번 및 건물번호", "small"), p("건물내역", "small")],
            [p("1", "body"), p("2017년 6월 20일", "body"), p("화곡동 123-45<br/>렌트가드빌 제3층 제301호", "body"), p("철근콘크리트구조<br/>42.18㎡", "body")],
        ], [18 * mm, 34 * mm, 75 * mm, 49 * mm], header_rows=1),
        p("【 갑구 】 소유권에 관한 사항", "section"),
        styled_table([
            [p("순위번호", "small"), p("등기목적", "small"), p("접수", "small"), p("등기원인", "small"), p("권리자 및 기타사항", "small")],
            [p("1", "body"), p("소유권보존", "body"), p("2017년 6월 22일<br/>제44521호", "body"), p("2017년 6월 20일", "body"), p("소유자 김민준<br/>서울특별시 강서구 테스트로 10", "body")],
        ], [15 * mm, 28 * mm, 36 * mm, 32 * mm, 65 * mm], header_rows=1),
        p("【 을구 】 소유권 이외의 권리에 관한 사항", "section"),
        styled_table([
            [p("순위번호", "small"), p("등기목적", "small"), p("접수", "small"), p("등기원인", "small"), p("권리자 및 기타사항", "small")],
            [p("1", "body"), p("근저당권설정", "body"), p("2024년 3월 12일<br/>제21988호", "body"), p("2024년 3월 12일<br/>설정계약", "body"), p("채권최고액 금110,000,000원<br/>채무자 김민준<br/>근저당권자 테스트은행", "body")],
        ], [15 * mm, 28 * mm, 36 * mm, 32 * mm, 65 * mm], header_rows=1),
        Spacer(1, 9 * mm),
        p("이 증명서는 RentGuard AI의 OCR 및 필드 추출 테스트를 위해 생성된 합성문서입니다. 실제 부동산, 인물, 금융기관과 관계가 없습니다.", "small"),
    ]
    document(path, story)


def make_ledger(path: Path):
    story = [
        p("일반건축물대장(갑)", "title"),
        p("테스트 전용 합성문서 · 발급번호 RG-LEDGER-0001", "subtitle"),
        Spacer(1, 4 * mm),
        styled_table([
            [p("대지위치", "small"), p("서울특별시 강서구 화곡동", "body"), p("지번", "small"), p("123-45", "body")],
            [p("도로명주소", "small"), p("서울특별시 강서구 화곡로 123", "body"), p("명칭", "small"), p("렌트가드빌", "body")],
            [p("대지면적", "small"), p("228.40㎡", "body"), p("연면적", "small"), p("512.73㎡", "body")],
            [p("건축면적", "small"), p("134.82㎡", "body"), p("건폐율", "small"), p("59.03%", "body")],
            [p("주용도", "small"), p("다세대주택", "body"), p("주구조", "small"), p("철근콘크리트구조", "body")],
            [p("층수", "small"), p("지하 0층 / 지상 5층", "body"), p("세대수", "small"), p("8세대", "body")],
            [p("허가일", "small"), p("2016. 11. 18.", "body"), p("사용승인일", "small"), p("2017. 06. 20.", "body")],
            [p("위반건축물 여부", "small"), p("해당 없음", "body"), p("변동사항", "small"), p("없음", "body")],
        ], [34 * mm, 57 * mm, 34 * mm, 51 * mm]),
        p("층별 개요", "section"),
        styled_table([
            [p("층", "small"), p("구조", "small"), p("용도", "small"), p("면적", "small")],
            [p("1층", "body"), p("철근콘크리트구조", "body"), p("주차장 / 계단실", "body"), p("82.51㎡", "body")],
            [p("2층", "body"), p("철근콘크리트구조", "body"), p("다세대주택(2세대)", "body"), p("107.34㎡", "body")],
            [p("3층", "body"), p("철근콘크리트구조", "body"), p("다세대주택(2세대)", "body"), p("107.34㎡", "body")],
            [p("4층", "body"), p("철근콘크리트구조", "body"), p("다세대주택(2세대)", "body"), p("107.34㎡", "body")],
            [p("5층", "body"), p("철근콘크리트구조", "body"), p("다세대주택(2세대)", "body"), p("108.20㎡", "body")],
        ], [25 * mm, 55 * mm, 65 * mm, 31 * mm], header_rows=1),
        Spacer(1, 10 * mm),
        p("이 문서는 국가법령정보센터의 건축물대장 서식 구조를 참고해 만든 테스트용 데이터입니다. 정부기관이 발급한 문서가 아닙니다.", "small"),
    ]
    document(path, story)


def make_contract(path: Path):
    story = [
        p("주택임대차계약서", "title"),
        p("보증금 있는 월세 · 테스트 전용 합성문서", "subtitle"),
        Spacer(1, 3 * mm),
        p("임대인 김민준과 임차인 이서연은 아래와 같이 임대차계약을 체결한다.", "body"),
        p("1. 임차주택의 표시", "section"),
        styled_table([
            [p("소재지", "small"), p("서울특별시 강서구 화곡로 123, 렌트가드빌 301호", "body")],
            [p("토지", "small"), p("대 228.40㎡", "body")],
            [p("건물", "small"), p("철근콘크리트구조 · 다세대주택 · 전유면적 42.18㎡", "body")],
            [p("임차할 부분", "small"), p("제3층 제301호 전부", "body")],
        ], [34 * mm, 142 * mm]),
        p("2. 계약 내용", "section"),
        styled_table([
            [p("보증금", "small"), p("금 일억오천만원정 (₩150,000,000)", "body")],
            [p("계약금", "small"), p("금 일천오백만원정 (₩15,000,000) - 계약 시 지급", "body")],
            [p("잔금", "small"), p("금 일억삼천오백만원정 (₩135,000,000) - 2026년 10월 10일 지급", "body")],
            [p("차임", "small"), p("월 금 십만원정 (₩100,000), 매월 10일 지급", "body")],
            [p("임대차 기간", "small"), p("2026년 10월 10일부터 2028년 10월 9일까지 (24개월)", "body")],
        ], [34 * mm, 142 * mm]),
        p("3. 특약사항", "section"),
        styled_table([
            [p("1", "small"), p("임대인은 잔금 지급일 전까지 등기부상 근저당권을 말소하고, 말소 확인 후 임차인이 잔금을 지급한다.", "body")],
            [p("2", "small"), p("임대인은 임차인의 전세보증금반환보증 가입에 필요한 서류 제출에 협조한다.", "body")],
            [p("3", "small"), p("임대인은 계약일부터 잔금 지급일 다음 날까지 새로운 담보권을 설정하지 않는다.", "body")],
        ], [14 * mm, 162 * mm]),
        p("4. 계약 당사자", "section"),
        styled_table([
            [p("구분", "small"), p("성명", "small"), p("주소", "small"), p("연락처", "small")],
            [p("임대인", "body"), p("김민준", "body"), p("서울특별시 강서구 테스트로 10", "body"), p("010-0000-0001", "body")],
            [p("임차인", "body"), p("이서연", "body"), p("서울특별시 마포구 샘플로 20", "body"), p("010-0000-0002", "body")],
        ], [24 * mm, 30 * mm, 82 * mm, 40 * mm], header_rows=1),
        Spacer(1, 9 * mm),
        p("작성일: 2026년 9월 7일", "body"),
        p("본 문서는 법무부 주택임대차표준계약서의 주요 필드 구성을 참고한 OCR 테스트용 합성문서이며 실제 계약으로 사용할 수 없습니다.", "small"),
    ]
    document(path, story)


def make_scanned_variant(source: Path, output: Path):
    prefix = TMP_DIR / "registry-page"
    subprocess.run(
        ["pdftoppm", "-f", "1", "-singlefile", "-r", "175", "-png", str(source), str(prefix)],
        check=True,
        capture_output=True,
    )
    image = Image.open(prefix.with_suffix(".png")).convert("L")
    image = ImageEnhance.Contrast(image).enhance(0.88)
    image = image.rotate(0.7, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=246)
    rng = random.Random(42)
    pixels = image.load()
    for _ in range(int(image.width * image.height * 0.0022)):
        x = rng.randrange(image.width)
        y = rng.randrange(image.height)
        pixels[x, y] = rng.choice((205, 218, 232, 245))
    image = image.filter(ImageFilter.GaussianBlur(radius=0.28)).convert("RGB")
    image.save(output, "PDF", resolution=175.0, quality=88)


def write_manifest(path: Path):
    manifest = {
        "fixture_version": "1.0.0",
        "notice": "All names, identifiers, addresses and institutions are synthetic test data.",
        "case_id": "RG-HIGH-001",
        "input": {"address": "서울특별시 강서구 화곡로 123", "deposit": 150000000, "monthly_rent": 100000},
        "expected": {
            "registry": {
                "owner": "김민준", "mortgage_amount": 110000000,
                "seizure": False, "provisional_seizure": False, "trust": False,
            },
            "building_ledger": {
                "building_use": "다세대주택", "is_illegal_building": False,
                "approval_date": "2017-06-20", "households": 8,
            },
            "lease_contract": {
                "landlord": "김민준", "tenant": "이서연", "deposit": 150000000,
                "monthly_rent": 100000, "lease_start": "2026-10-10", "lease_end": "2028-10-09",
            },
            "cross_checks": {"owner_matches_landlord": True, "deposit_matches_input": True},
            "risk": {"score": 73, "grade": "높음"},
        },
        "files": [
            {"name": "registry_risky_digital.pdf", "kind": "registry", "mode": "digital_text"},
            {"name": "registry_risky_scan_noisy.pdf", "kind": "registry", "mode": "image_only_noisy_scan"},
            {"name": "building_ledger_risky.pdf", "kind": "building_ledger", "mode": "digital_text"},
            {"name": "lease_contract_risky.pdf", "kind": "lease_contract", "mode": "digital_text"},
        ],
    }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    registry = OUTPUT_DIR / "registry_risky_digital.pdf"
    make_registry(registry)
    make_ledger(OUTPUT_DIR / "building_ledger_risky.pdf")
    make_contract(OUTPUT_DIR / "lease_contract_risky.pdf")
    make_scanned_variant(registry, OUTPUT_DIR / "registry_risky_scan_noisy.pdf")
    write_manifest(OUTPUT_DIR / "ground_truth.json")
    print(OUTPUT_DIR)


if __name__ == "__main__":
    main()
