"""Compare a registry PDF extraction against the fixture ground truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.services.registry_evaluator import evaluate_registry  # noqa: E402
from app.services.registry_parser import extract_registry  # noqa: E402


def main() -> int:
    default_fixture = ROOT / "output" / "pdf" / "rentguard-fixtures"
    parser = argparse.ArgumentParser(description="Evaluate RentGuard registry extraction")
    parser.add_argument("--pdf", type=Path, default=default_fixture / "registry_risky_digital.pdf")
    parser.add_argument("--ground-truth", type=Path, default=default_fixture / "ground_truth.json")
    parser.add_argument("--no-ocr", action="store_true", help="Fail instead of using OCR fallback")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()

    expected = json.loads(args.ground_truth.read_text(encoding="utf-8"))["expected"]["registry"]
    result = extract_registry(args.pdf.read_bytes(), allow_ocr=not args.no_ocr)
    evaluation = evaluate_registry(result, expected)

    if args.json:
        print(json.dumps({
            "extraction": result.model_dump(mode="json"),
            "evaluation": evaluation.model_dump(mode="json"),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"PDF: {args.pdf.name}")
        print(f"Method: {result.extraction_method} / Confidence: {result.confidence:.3f}")
        for item in evaluation.comparisons:
            status = "PASS" if item.passed else "FAIL"
            print(f"{status:4}  {item.field:22} expected={item.expected!r} actual={item.actual!r}")
        print(f"Result: {evaluation.matched}/{evaluation.total} ({evaluation.accuracy:.0%})")
    return 0 if evaluation.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
