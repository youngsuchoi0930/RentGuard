from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from threading import Lock

from pypdf import PdfReader


@dataclass(frozen=True)
class ExtractedPage:
    number: int
    text: str
    confidence: float


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[ExtractedPage]
    method: str

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


class OCRUnavailableError(RuntimeError):
    pass


_ocr_engine = None
_ocr_lock = Lock()


def _has_meaningful_text(pages: list[ExtractedPage]) -> bool:
    content = "".join(page.text for page in pages)
    letters = sum(char.isalnum() for char in content)
    return letters >= 30


def _extract_pdf_text(data: bytes) -> list[ExtractedPage]:
    reader = PdfReader(BytesIO(data))
    return [
        ExtractedPage(number=index, text=page.extract_text() or "", confidence=1.0)
        for index, page in enumerate(reader.pages, start=1)
    ]


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is not None:
        return _ocr_engine
    with _ocr_lock:
        if _ocr_engine is None:
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise OCRUnavailableError(
                    "OCR dependencies are unavailable. Install paddleocr and paddlepaddle."
                ) from exc
            _ocr_engine = PaddleOCR(
                text_detection_model_name="PP-OCRv5_mobile_det",
                text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                enable_mkldnn=False,
            )
    return _ocr_engine


def _payload_from_result(result) -> dict:
    payload = getattr(result, "json", {})
    if callable(payload):
        payload = payload()
    if isinstance(payload, dict) and isinstance(payload.get("res"), dict):
        return payload["res"]
    return payload if isinstance(payload, dict) else {}


def _extract_ocr(data: bytes) -> list[ExtractedPage]:
    try:
        import pymupdf
        import numpy as np
        from PIL import Image
    except ImportError as exc:
        raise OCRUnavailableError("PDF rendering dependencies are unavailable.") from exc

    engine = _get_ocr_engine()
    pdf = pymupdf.open(stream=data, filetype="pdf")
    pages: list[ExtractedPage] = []
    for number, page in enumerate(pdf, start=1):
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.2, 2.2), alpha=False)
        image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
        results = engine.predict(np.asarray(image))
        texts: list[str] = []
        scores: list[float] = []
        for result in results:
            payload = _payload_from_result(result)
            texts.extend(str(text) for text in payload.get("rec_texts", []) if str(text).strip())
            scores.extend(float(score) for score in payload.get("rec_scores", []))
        confidence = sum(scores) / len(scores) if scores else 0.0
        pages.append(ExtractedPage(number=number, text="\n".join(texts), confidence=confidence))
    return pages


def extract_pdf(data: bytes, *, allow_ocr: bool = True) -> ExtractedDocument:
    pages = _extract_pdf_text(data)
    if _has_meaningful_text(pages):
        return ExtractedDocument(pages=pages, method="pdf_text")
    if not allow_ocr:
        raise OCRUnavailableError("The PDF has no usable text layer and OCR is disabled.")
    return ExtractedDocument(pages=_extract_ocr(data), method="ocr")
