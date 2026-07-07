from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    RectangleObject,
    TextStringObject,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.pdf_tools import clean_pdf, write_report


EXAMPLE_DIR = ROOT / "docs" / "examples"
INPUT_PDF = EXAMPLE_DIR / "demo-statement.pdf"
CLEAN_PDF = EXAMPLE_DIR / "demo-statement-clean.pdf"
REPORT_JSON = EXAMPLE_DIR / "demo-report.json"


def pdf_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_line(x: int, y: int, size: int, text: str) -> str:
    return f"BT /F1 {size} Tf {x} {y} Td ({pdf_string(text)}) Tj ET"


def create_demo_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)

    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    ext_gstate = DictionaryObject(
        {
            NameObject("/GS1"): DictionaryObject(
                {
                    NameObject("/Type"): NameObject("/ExtGState"),
                    NameObject("/ca"): FloatObject(0.22),
                    NameObject("/CA"): FloatObject(0.22),
                }
            )
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            NameObject("/ExtGState"): ext_gstate,
        }
    )

    lines = [
        "PDF Clean Demo Statement",
        "Generated sample document - no real account data.",
        "Date        Description              Debit     Credit    Balance",
        "2026-07-01  Opening balance                              8,240.00",
        "2026-07-02  Example vendor payment       120.00             8,120.00",
        "2026-07-03  Example customer receipt               560.00    8,680.00",
        "2026-07-04  Office supplies               48.35             8,631.65",
        "2026-07-05  Service fee                     6.00             8,625.65",
        "2026-07-06  Demo transfer                            1,000.00 9,625.65",
    ]

    content = [
        "q",
        "0.96 0.97 0.98 rg 0 0 612 792 re f",
        "Q",
        text_line(72, 724, 18, lines[0]),
        text_line(72, 696, 10, lines[1]),
        "0.12 0.15 0.18 rg",
    ]
    y = 646
    for index, line in enumerate(lines[2:]):
        size = 10 if index else 11
        content.append(text_line(72, y, size, line))
        y -= 28

    content.extend(
        [
            "q",
            "/GS1 gs",
            "0.9 0.1 0.1 rg",
            "0.707 0.707 -0.707 0.707 175 265 cm",
            "BT /F1 56 Tf 0 0 Td (DEMO WATERMARK) Tj ET",
            "Q",
            "q",
            "1 1 1 rg 410 92 130 45 re f",
            "0.95 0.2 0.1 RG 2 w 410 92 130 45 re S",
            "0.95 0.2 0.1 rg",
            "BT /F1 14 Tf 424 111 Td (SIGNED DEMO) Tj ET",
            "Q",
        ]
    )

    stream = DecodedStreamObject()
    stream.set_data(("\n".join(content) + "\n").encode("ascii"))
    page[NameObject("/Contents")] = stream

    signature_widget = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Sig"),
            NameObject("/T"): TextStringObject("DemoSignature"),
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Rect"): RectangleObject([410, 92, 540, 137]),
            NameObject("/F"): NumberObject(4),
            NameObject("/P"): page.indirect_reference,
        }
    )
    signature_ref = writer._add_object(signature_widget)
    page[NameObject("/Annots")] = ArrayObject([signature_ref])
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject([signature_ref]),
            NameObject("/SigFlags"): NumberObject(3),
        }
    )
    writer.add_metadata(
        {
            "/Title": "PDF Clean Demo Statement",
            "/Subject": "Synthetic sample for PDF Clean",
            "/Creator": "PDF Clean",
        }
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def main() -> int:
    create_demo_pdf(INPUT_PDF)
    report = clean_pdf(INPUT_PDF, CLEAN_PDF)
    report.input = str(INPUT_PDF.relative_to(ROOT))
    report.output = str(CLEAN_PDF.relative_to(ROOT))
    write_report(report, REPORT_JSON)

    reader = PdfReader(str(CLEAN_PDF), strict=False)
    if len(reader.pages) != 1:
        raise SystemExit("Demo clean output should keep one page.")
    if report.signature_fields_removed != 1 or report.signature_widgets_removed != 1:
        raise SystemExit("Demo cleanup did not remove the synthetic signature structures.")
    print(f"Wrote {INPUT_PDF.relative_to(ROOT)}")
    print(f"Wrote {CLEAN_PDF.relative_to(ROOT)}")
    print(f"Wrote {REPORT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
