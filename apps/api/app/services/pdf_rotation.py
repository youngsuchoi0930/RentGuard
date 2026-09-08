from __future__ import annotations

import argparse
from pathlib import Path

import pymupdf


SUPPORTED_ROTATIONS = {90, 180, 270}


def rotate_pdf(
    input_path: str | Path,
    output_path: str | Path,
    rotation: int = 90,
) -> Path:
    """Create a physically rotated PDF copy without modifying the source file.

    Page contents are placed into newly created pages, so the result does not
    depend on the PDF ``/Rotate`` viewer flag. Links, annotations, and form
    widgets are not copied by ``show_pdf_page`` and should be handled by a
    separate workflow when present.
    """
    if rotation not in SUPPORTED_ROTATIONS:
        raise ValueError("rotation must be one of 90, 180, or 270 degrees")

    source = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if source == destination:
        raise ValueError("output_path must be different from input_path")
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError(destination)

    destination.parent.mkdir(parents=True, exist_ok=True)

    with pymupdf.open(source) as source_pdf, pymupdf.open() as rotated_pdf:
        if not source_pdf.is_pdf:
            raise ValueError("input_path must point to a PDF file")

        for page_number, source_page in enumerate(source_pdf):
            source_rect = source_page.rect
            if rotation in {90, 270}:
                width, height = source_rect.height, source_rect.width
            else:
                width, height = source_rect.width, source_rect.height

            target_page = rotated_pdf.new_page(width=width, height=height)
            target_page.show_pdf_page(
                target_page.rect,
                source_pdf,
                page_number,
                rotate=rotation,
                keep_proportion=True,
            )

        rotated_pdf.save(destination, garbage=4, deflate=True)

    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a physically rotated PDF copy while preserving the original."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rotation", type=int, choices=sorted(SUPPORTED_ROTATIONS), default=90)
    args = parser.parse_args()
    rotate_pdf(args.input, args.output, args.rotation)


if __name__ == "__main__":
    main()
