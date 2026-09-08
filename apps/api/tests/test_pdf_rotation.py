from pathlib import Path

import pymupdf
import pytest

from app.services.pdf_rotation import rotate_pdf


def _make_source_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=300, height=500)
        page.insert_text((40, 60), "RentGuard rotation test")
        document.save(path)


@pytest.mark.parametrize(
    ("rotation", "expected_size"),
    [(90, (500, 300)), (180, (300, 500)), (270, (500, 300))],
)
def test_rotate_pdf_creates_flattened_copy_without_changing_source(
    tmp_path: Path,
    rotation: int,
    expected_size: tuple[int, int],
) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / f"rotated-{rotation}.pdf"
    _make_source_pdf(source)
    original_bytes = source.read_bytes()

    result = rotate_pdf(source, destination, rotation)

    assert result == destination.resolve()
    assert source.read_bytes() == original_bytes
    with pymupdf.open(destination) as document:
        assert document.page_count == 1
        page = document[0]
        assert (round(page.rect.width), round(page.rect.height)) == expected_size
        assert page.rotation == 0
        assert "RentGuard rotation test" in page.get_text()


def test_rotate_pdf_rejects_unsupported_rotation(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    _make_source_pdf(source)

    with pytest.raises(ValueError, match="90, 180, or 270"):
        rotate_pdf(source, tmp_path / "output.pdf", 45)


def test_rotate_pdf_never_overwrites_source_or_existing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    destination = tmp_path / "output.pdf"
    _make_source_pdf(source)
    _make_source_pdf(destination)

    with pytest.raises(ValueError, match="different"):
        rotate_pdf(source, source)
    with pytest.raises(FileExistsError):
        rotate_pdf(source, destination)
