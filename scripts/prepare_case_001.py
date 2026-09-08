from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = Path(r"C:\RentGuard-private-raw\case-001")
DEFAULT_OUTPUT = REPO_ROOT / "local-fixtures" / "case-001"

SCALE = 2.0
OWNER = "홍길동"
TENANT = "이서연"
ROAD_ADDRESS = "서울특별시 테스트구 안전로 123, 201호"
LOT_ADDRESS = "서울특별시 테스트구 안전동 123-45"
BUILDING_NAME = "렌트가드빌"
MORTGAGE_HOLDER = "테스트은행"
DEPOSIT = 150_000_000
MONTHLY_RENT = 100_000
MORTGAGE_AMOUNT = 110_000_000

REGULAR_FONT_PATH = Path(r"C:\Windows\Fonts\malgun.ttf")
BOLD_FONT_PATH = Path(r"C:\Windows\Fonts\malgunbd.ttf")


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = BOLD_FONT_PATH if bold else REGULAR_FONT_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Korean font is unavailable: {path}")
    return ImageFont.truetype(str(path), round(size * SCALE))


def _box(points: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    return tuple(round(value * SCALE) for value in points)  # type: ignore[return-value]


def _point(points: tuple[float, float]) -> tuple[int, int]:
    return tuple(round(value * SCALE) for value in points)  # type: ignore[return-value]


def _cover(draw: ImageDraw.ImageDraw, points: tuple[float, float, float, float]) -> None:
    draw.rectangle(_box(points), fill="white")


def _write(
    draw: ImageDraw.ImageDraw,
    points: tuple[float, float],
    text: str,
    *,
    size: int = 8,
    bold: bool = False,
    fill: str = "black",
    spacing: int = 2,
) -> None:
    draw.multiline_text(
        _point(points),
        text,
        font=_font(size, bold=bold),
        fill=fill,
        spacing=round(spacing * SCALE),
    )


def _check(draw: ImageDraw.ImageDraw, points: tuple[float, float], size: float = 9) -> None:
    x, y = points
    width = max(1, round(1.3 * SCALE))
    draw.line(
        [_point((x, y + size * 0.55)), _point((x + size * 0.35, y + size))],
        fill="black",
        width=width,
    )
    draw.line(
        [_point((x + size * 0.35, y + size)), _point((x + size, y))],
        fill="black",
        width=width,
    )


def _watermark(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    text = "RentGuard AI 개발 테스트용 - 개인정보 익명화 - 법적 효력 없음"
    font = _font(8, bold=True)
    bounds = draw.textbbox((0, 0), text, font=font)
    text_width = bounds[2] - bounds[0]
    draw.rectangle(
        (0, height - round(18 * SCALE), width, height),
        fill=(255, 244, 244),
    )
    draw.text(
        ((width - text_width) // 2, height - round(15 * SCALE)),
        text,
        font=font,
        fill=(170, 20, 20),
    )


def _render(pdf_path: Path) -> list[Image.Image]:
    pages: list[Image.Image] = []
    with pymupdf.open(pdf_path) as document:
        for page in document:
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(SCALE, SCALE), alpha=False)
            pages.append(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
    return pages


def _save_raster_pdf(pages: list[Image.Image], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as output:
        for image in pages:
            width = image.width / SCALE
            height = image.height / SCALE
            page = output.new_page(width=width, height=height)
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            page.insert_image(page.rect, stream=buffer.getvalue())
        output.set_metadata({})
        output.save(output_path, garbage=4, deflate=True)


def _sanitize_registry(source: Path, output: Path) -> None:
    pages = _render(source)
    if len(pages) != 3:
        raise ValueError(f"Expected a three-page registry, found {len(pages)} pages")

    first = ImageDraw.Draw(pages[0])
    _cover(first, (430, 116, 578, 164))
    _write(first, (438, 124), "고유번호 TEST-0000-000000", size=8, bold=True)
    _cover(first, (22, 158, 578, 181))
    _write(first, (25, 162), f"[집합건물] {ROAD_ADDRESS}", size=8)
    _cover(first, (156, 226, 435, 437))
    _write(
        first,
        (164, 235),
        f"{LOT_ADDRESS}\n[도로명주소]\n{ROAD_ADDRESS}\n\n철근콘크리트조\n공동주택\n제2층 제201호",
        size=8,
        spacing=3,
    )
    _cover(first, (76, 480, 357, 592))
    _write(
        first,
        (82, 490),
        "1. 서울특별시 테스트구 안전동 123-45\n"
        "2. 서울특별시 테스트구 안전동 123-46\n"
        "3. 서울특별시 테스트구 안전동 123-47\n"
        "4. 서울특별시 테스트구 안전동 123-48",
        size=8,
        spacing=5,
    )
    _cover(first, (21, 775, 235, 807))
    _write(first, (25, 782), "열람일시 : 2026년09월08일", size=8)
    _watermark(first, pages[0].width, pages[0].height)

    second = ImageDraw.Draw(pages[1])
    _cover(second, (22, 79, 578, 123))
    _write(second, (25, 88), f"[집합건물] {ROAD_ADDRESS}", size=8)
    _cover(second, (76, 147, 355, 188))
    _write(second, (82, 156), "제2층 제201호        철근콘크리트조 84.59㎡", size=8)
    _cover(second, (340, 320, 574, 493))
    _write(
        second,
        (350, 331),
        f"공유자  지분 2분의 1\n소유자 {OWNER}\n900101-1******\n{ROAD_ADDRESS}\n\n"
        f"공유자  지분 2분의 1\n소유자 {OWNER}\n900101-1******\n{ROAD_ADDRESS}\n"
        "거래가액 금220,000,000원",
        size=8,
        spacing=3,
    )
    _cover(second, (340, 494, 574, 556))
    _write(second, (350, 505), f"공유자  지분 2분의 1\n소유자 {OWNER}\n{ROAD_ADDRESS}", size=8)
    _cover(second, (340, 570, 575, 690))
    _write(
        second,
        (350, 580),
        f"채권최고액 금{MORTGAGE_AMOUNT:,}원\n채무자 {OWNER}\n{ROAD_ADDRESS}",
        size=8,
        spacing=4,
    )
    _cover(second, (21, 775, 235, 807))
    _write(second, (25, 782), "열람일시 : 2026년09월08일", size=8)
    _watermark(second, pages[1].width, pages[1].height)

    third = ImageDraw.Draw(pages[2])
    _cover(third, (22, 57, 578, 84))
    _write(third, (25, 63), f"[집합건물] {ROAD_ADDRESS}", size=8)
    _cover(third, (338, 104, 575, 180))
    _write(
        third,
        (350, 116),
        f"근저당권자 {MORTGAGE_HOLDER}\n법인번호 TEST-000000\n서울특별시 테스트구 안전로 1",
        size=8,
        spacing=4,
    )
    _cover(third, (21, 775, 235, 807))
    _write(third, (25, 782), "열람일시 : 2026년09월08일", size=8)
    _watermark(third, pages[2].width, pages[2].height)

    _save_raster_pdf(pages, output)


def _sanitize_building(source: Path, output: Path) -> None:
    pages = _render(source)
    if len(pages) != 2:
        raise ValueError(f"Expected a two-page building ledger, found {len(pages)} pages")

    first = ImageDraw.Draw(pages[0])
    _cover(first, (16, 15, 330, 45))
    _write(first, (20, 22), "문서확인번호: TEST-0000-0000", size=8, bold=True)
    _cover(first, (16, 45, 130, 100))
    _cover(first, (737, 18, 824, 91))
    _write(first, (755, 45), "QR 제거", size=9, bold=True, fill="#666666")
    _cover(first, (40, 65, 805, 153))
    _write(
        first,
        (135, 70),
        "집합건축물대장 전유부\n"
        f"명칭 {BUILDING_NAME}\n"
        f"대지위치 {LOT_ADDRESS}\n"
        f"도로명주소 {ROAD_ADDRESS}\n"
        "주용도 공동주택\n"
        "주구조 철근콘크리트\n"
        "위반건축물 여부 해당없음",
        size=7,
        spacing=2,
    )
    _cover(first, (416, 171, 721, 312))
    _write(
        first,
        (426, 181),
        f"성명(명칭)  {OWNER}\n주민등록번호  900101-1******\n주소  {ROAD_ADDRESS}\n"
        "소유권 지분  1/1\n변동일자  2026. 9. 8.\n변동원인  테스트용 가명 처리",
        size=8,
        spacing=5,
    )
    _cover(first, (486, 369, 824, 458))
    _write(first, (500, 385), "발급일: 2026년 09월 08일\n테스트 발급본\n연락처 제거", size=8, spacing=5)
    _cover(first, (18, 505, 824, 572))
    _write(first, (340, 530), "전자검증 코드 및 QR 제거됨", size=10, bold=True, fill="#666666")
    _watermark(first, pages[0].width, pages[0].height)

    second = ImageDraw.Draw(pages[1])
    _cover(second, (16, 15, 330, 45))
    _cover(second, (737, 18, 824, 91))
    _write(second, (755, 45), "QR 제거", size=9, bold=True, fill="#666666")
    _cover(second, (40, 65, 805, 153))
    _write(
        second,
        (135, 75),
        "CASE-001 익명화 부속 페이지",
        size=8,
    )
    _cover(second, (18, 505, 824, 572))
    _write(second, (340, 530), "전자검증 코드 및 QR 제거됨", size=10, bold=True, fill="#666666")
    _watermark(second, pages[1].width, pages[1].height)

    _save_raster_pdf(pages, output)


def _fill_contract(source: Path, output: Path) -> None:
    pages = _render(source)
    if len(pages) != 5:
        raise ValueError(f"Expected a five-page contract template, found {len(pages)} pages")

    first = ImageDraw.Draw(pages[0])
    _cover(first, (35, 90, 575, 112))
    _write(
        first,
        (45, 96),
        f"임대인 {OWNER}과 임차인 {TENANT}은 아래와 같이 임대차계약을 체결한다.",
        size=8,
        bold=True,
    )
    _check(first, (466, 77), size=9)
    _cover(first, (110, 143, 575, 161))
    _write(first, (110, 144), ROAD_ADDRESS, size=8, bold=True)
    _cover(first, (110, 162, 328, 182))
    _write(first, (118, 165), "123-45", size=8)
    _cover(first, (380, 162, 575, 182))
    _write(first, (383, 165), "153.70", size=8)
    _cover(first, (110, 182, 328, 203))
    _write(first, (118, 185), "철근콘크리트조 공동주택", size=8)
    _cover(first, (380, 182, 575, 203))
    _write(first, (383, 185), "84.59", size=8)
    _cover(first, (110, 203, 328, 222))
    _write(first, (118, 205), "제2층 제201호", size=8)
    _cover(first, (380, 203, 575, 222))
    _write(first, (383, 205), "84.59", size=8)
    _check(first, (110, 211), size=7)
    _cover(first, (145, 244, 575, 265))
    _write(first, (155, 251), "임대차기간 2026.09.08 ~ 2028.09.07", size=8, bold=True)
    _cover(first, (35, 395, 575, 508))
    _write(first, (45, 399), "보증금 150,000,000원", size=8, bold=True)
    _write(first, (45, 421), "계약금 15,000,000원", size=8)
    _write(first, (45, 444), "중도금 0원", size=8)
    _write(first, (45, 466), "잔금 135,000,000원", size=8)
    _write(first, (45, 488), "차임 100,000원, 매월 8일", size=8, bold=True)
    _cover(first, (395, 645, 575, 672))
    _write(first, (405, 653), "2026.09.08 ~ 2028.09.07", size=7, bold=True)
    _watermark(first, pages[0].width, pages[0].height)

    second = ImageDraw.Draw(pages[1])
    _cover(second, (34, 605, 575, 780))
    _write(
        second,
        (42, 615),
        "1. 잔금 지급 전 근저당권을 말소한다.\n"
        "2. 임대인은 계약 기간 동안 추가 담보권을 설정하지 않는다.\n"
        "3. 보증보험 가입 불가 시 계약금을 반환한다.",
        size=8,
        bold=True,
        spacing=7,
    )
    _watermark(second, pages[1].width, pages[1].height)

    third = ImageDraw.Draw(pages[2])
    _cover(third, (480, 72, 575, 92))
    _write(third, (485, 77), "2026년 09월 08일", size=7, bold=True)
    _cover(third, (125, 138, 575, 164))
    _write(third, (128, 145), ROAD_ADDRESS, size=7)
    _cover(third, (125, 164, 575, 191))
    _write(third, (128, 170), "900101-1******", size=8)
    _write(third, (339, 170), "010-0000-0000", size=8)
    _write(third, (445, 170), OWNER, size=8, bold=True)
    _cover(third, (125, 211, 575, 237))
    _write(third, (128, 216), "서울특별시 테스트구 평화로 45", size=7)
    _cover(third, (125, 237, 575, 263))
    _write(third, (128, 242), "950202-2******", size=8)
    _write(third, (339, 242), "010-0000-0000", size=8)
    _write(third, (445, 242), TENANT, size=8, bold=True)
    _watermark(third, pages[2].width, pages[2].height)

    for page in pages[3:]:
        _watermark(ImageDraw.Draw(page), page.width, page.height)

    _save_raster_pdf(pages, output)


def _write_expected(output_path: Path) -> None:
    expected = {
        "case_id": "CASE-001",
        "source_type": "real_layout_sanitized",
        "input": {
            "address": ROAD_ADDRESS,
            "deposit": DEPOSIT,
            "monthly_rent": MONTHLY_RENT,
        },
        "expected": {
            "registry": {
                "owners": [OWNER],
                "road_address": ROAD_ADDRESS,
                "mortgages": [
                    {
                        "holder": MORTGAGE_HOLDER,
                        "debtor": OWNER,
                        "maximum_claim_amount": MORTGAGE_AMOUNT,
                    }
                ],
            },
            "building_ledger": {
                "road_address": ROAD_ADDRESS,
                "building_name": BUILDING_NAME,
                "main_use": "공동주택",
                "is_illegal_building": False,
            },
            "lease_contract": {
                "landlord": OWNER,
                "tenant": TENANT,
                "address": ROAD_ADDRESS,
                "deposit": DEPOSIT,
                "monthly_rent": MONTHLY_RENT,
                "lease_start": "2026-09-08",
                "lease_end": "2028-09-07",
            },
            "cross_checks": {
                "owner_landlord_match": True,
                "property_address_match": True,
                "deposit_match": True,
                "monthly_rent_match": True,
            },
        },
    }
    output_path.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_case(source_dir: Path, output_dir: Path) -> None:
    outputs = [
        output_dir / "registry.pdf",
        output_dir / "building-ledger.pdf",
        output_dir / "lease-contract.pdf",
        output_dir / "expected.json",
    ]
    existing = [path for path in outputs if path.exists()]
    if existing:
        raise FileExistsError(f"Refusing to overwrite existing outputs: {existing}")

    _sanitize_registry(source_dir / "registry-original.pdf", output_dir / "registry.pdf")
    _sanitize_building(
        source_dir / "building-ledger-upright-private.pdf",
        output_dir / "building-ledger.pdf",
    )
    _fill_contract(source_dir / "lease-contract-template.pdf", output_dir / "lease-contract.pdf")
    _write_expected(output_dir / "expected.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the sanitized CASE-001 fixture bundle.")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    prepare_case(args.source_dir.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    main()
