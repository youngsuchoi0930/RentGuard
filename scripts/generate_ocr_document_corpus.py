"""Create image-only scan variants from the synthetic document corpus."""

from __future__ import annotations

import json
import random
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "output" / "pdf" / "rentguard-synthetic-corpus"
OUTPUT_DIR = ROOT / "output" / "pdf" / "rentguard-ocr-corpus"
SOURCE_PDF = SOURCE_DIR / "rentguard-synthetic-corpus-30.pdf"
SOURCE_MANIFEST = SOURCE_DIR / "manifest.json"
OUTPUT_PDF = OUTPUT_DIR / "rentguard-ocr-corpus-10.pdf"
OUTPUT_MANIFEST = OUTPUT_DIR / "manifest.json"


SELECTION = (
    ("RG-SYN-001", "clean_gray", 190, 0.0, 1.00, 0.00, 0.0000, 92),
    ("RG-SYN-006", "slight_clockwise", 185, 0.35, 0.98, 0.10, 0.0000, 90),
    ("RG-SYN-010", "slight_counterclockwise", 185, -0.45, 1.00, 0.10, 0.0000, 90),
    ("RG-SYN-014", "soft_scan", 180, 0.0, 0.94, 0.22, 0.0000, 88),
    ("RG-SYN-016", "faint_copy", 185, 0.15, 0.82, 0.12, 0.0000, 90),
    ("RG-SYN-018", "dark_copy", 185, -0.20, 1.18, 0.10, 0.0000, 90),
    ("RG-SYN-020", "light_speckle", 185, 0.25, 0.96, 0.08, 0.00035, 88),
    ("RG-SYN-023", "low_resolution", 155, 0.0, 1.00, 0.12, 0.0000, 86),
    ("RG-SYN-026", "compressed_scan", 175, -0.30, 0.93, 0.18, 0.0002, 78),
    ("RG-SYN-030", "mixed_scan", 170, 0.40, 0.90, 0.20, 0.0003, 82),
)


def _degrade(
    image: Image.Image,
    *,
    rotation: float,
    contrast: float,
    blur: float,
    noise_ratio: float,
    seed: int,
) -> Image.Image:
    result = image.convert("L")
    result = ImageEnhance.Contrast(result).enhance(contrast)
    if blur:
        result = result.filter(ImageFilter.GaussianBlur(radius=blur))
    if rotation:
        result = result.rotate(
            rotation,
            resample=Image.Resampling.BICUBIC,
            expand=False,
            fillcolor=248,
        )
    if noise_ratio:
        rng = random.Random(seed)
        pixels = result.load()
        count = int(result.width * result.height * noise_ratio)
        for _ in range(count):
            x = rng.randrange(result.width)
            y = rng.randrange(result.height)
            pixels[x, y] = rng.choice((185, 205, 225, 242))
    return result.convert("RGB")


def _jpeg_bytes(image: Image.Image, quality: int) -> bytes:
    stream = BytesIO()
    image.save(stream, format="JPEG", quality=quality, optimize=True, dpi=(180, 180))
    return stream.getvalue()


def generate() -> tuple[Path, Path]:
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    cases_by_id = {case["case_id"]: case for case in source_manifest["cases"]}
    source_pdf = pymupdf.open(SOURCE_PDF)
    output_pdf = pymupdf.open()
    manifest_cases = []

    for case_index, selection in enumerate(SELECTION):
        case_id, profile, dpi, rotation, contrast, blur, noise_ratio, quality = selection
        source_case = cases_by_id[case_id]
        output_pages: dict[str, int] = {}
        for document_index, document_kind in enumerate(
            ("registry", "building_ledger", "lease_contract")
        ):
            source_page_number = source_case["pages"][document_kind]
            source_page = source_pdf[source_page_number - 1]
            pixmap = source_page.get_pixmap(dpi=dpi, alpha=False)
            image = Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            degraded = _degrade(
                image,
                rotation=rotation,
                contrast=contrast,
                blur=blur,
                noise_ratio=noise_ratio,
                seed=(case_index + 1) * 100 + document_index,
            )
            target_page = output_pdf.new_page(
                width=source_page.rect.width,
                height=source_page.rect.height,
            )
            target_page.insert_image(
                target_page.rect,
                stream=_jpeg_bytes(degraded, quality),
            )
            output_pages[document_kind] = len(output_pdf)

        manifest_cases.append({
            **source_case,
            "source_kind": "synthetic_ocr",
            "source_case_id": case_id,
            "ocr_profile": {
                "name": profile,
                "dpi": dpi,
                "rotation_degrees": rotation,
                "contrast": contrast,
                "blur_radius": blur,
                "noise_ratio": noise_ratio,
                "jpeg_quality": quality,
            },
            "pages": output_pages,
        })

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_pdf.save(OUTPUT_PDF, garbage=4, deflate=True)
    output_pdf.close()
    source_pdf.close()

    manifest = {
        "corpus_version": "1.0.0",
        "source_kind": "synthetic_ocr",
        "notice": (
            "Image-only derivatives of fictional RentGuard synthetic documents. "
            "Use only for OCR regression testing, never for real-world accuracy claims."
        ),
        "case_count": len(manifest_cases),
        "documents_per_case": 3,
        "page_count": len(manifest_cases) * 3,
        "pdf": OUTPUT_PDF.name,
        "cases": manifest_cases,
    }
    OUTPUT_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return OUTPUT_PDF, OUTPUT_MANIFEST


def main() -> None:
    pdf_path, manifest_path = generate()
    print(pdf_path)
    print(manifest_path)


if __name__ == "__main__":
    main()
