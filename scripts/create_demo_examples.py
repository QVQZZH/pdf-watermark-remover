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
BEFORE_PNG = EXAMPLE_DIR / "demo-before.png"
AFTER_PNG = EXAMPLE_DIR / "demo-after.png"
COMPARISON_PNG = EXAMPLE_DIR / "demo-comparison.png"

STATEMENT_ROWS = [
    "Date        Description              Debit     Credit    Balance",
    "2026-07-01  Opening balance                              8,240.00",
    "2026-07-02  Example vendor payment       120.00             8,120.00",
    "2026-07-03  Example customer receipt               560.00    8,680.00",
    "2026-07-04  Office supplies               48.35             8,631.65",
    "2026-07-05  Service fee                     6.00             8,625.65",
    "2026-07-06  Demo transfer                            1,000.00 9,625.65",
]
STATEMENT_TABLE = [
    ("Date", "Description", "Debit", "Credit", "Balance"),
    ("2026-07-01", "Opening balance", "", "", "8,240.00"),
    ("2026-07-02", "Vendor payment", "120.00", "", "8,120.00"),
    ("2026-07-03", "Customer receipt", "", "560.00", "8,680.00"),
    ("2026-07-04", "Office supplies", "48.35", "", "8,631.65"),
    ("2026-07-05", "Service fee", "6.00", "", "8,625.65"),
    ("2026-07-06", "Demo transfer", "", "1,000.00", "9,625.65"),
]


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

    content = [
        "q",
        "0.96 0.97 0.98 rg 0 0 612 792 re f",
        "Q",
        text_line(72, 724, 18, "PDF Clean Demo Statement"),
        text_line(72, 696, 10, "Generated sample document - no real account data."),
        "0.12 0.15 0.18 rg",
    ]
    y = 646
    for index, line in enumerate(STATEMENT_ROWS):
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


def create_preview_png(path: Path, *, cleaned: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont

    scale = 2
    width, height = 612, 792
    image = Image.new("RGB", (width * scale, height * scale), "#f5f7f9")
    draw = ImageDraw.Draw(image, "RGBA")

    def xy(x: int, y: int) -> tuple[int, int]:
        return x * scale, y * scale

    def box(rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = rect
        return x0 * scale, y0 * scale, x1 * scale, y1 * scale

    title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 28 * scale)
    body_font = ImageFont.truetype("DejaVuSans.ttf", 13 * scale)
    body_bold_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 13 * scale)
    small_font = ImageFont.truetype("DejaVuSans.ttf", 13 * scale)
    stamp_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 17 * scale)
    watermark_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 48 * scale)

    draw.rectangle(box((44, 44, 568, 748)), fill="#ffffff", outline="#d8dde3", width=2 * scale)
    draw.text(xy(72, 82), "PDF Clean Demo Statement", fill="#151719", font=title_font)
    draw.text(xy(72, 122), "Generated sample document - no real account data.", fill="#66707a", font=small_font)

    columns = [72, 172, 344, 420, 500]
    right_aligned = {2, 3, 4}
    y = 176
    for row_index, row in enumerate(STATEMENT_TABLE):
        font = body_bold_font if row_index == 0 else body_font
        fill = "#151719" if row_index == 0 else "#2d333a"
        if row_index == 1:
            draw.line((72 * scale, (y - 12) * scale, 540 * scale, (y - 12) * scale), fill="#e4e7ec", width=1 * scale)
        for column_index, value in enumerate(row):
            if column_index in right_aligned:
                text_width = draw.textlength(value, font=font)
                draw.text((columns[column_index] * scale - text_width, y * scale), value, fill=fill, font=font)
            else:
                draw.text(xy(columns[column_index], y), value, fill=fill, font=font)
        y += 34

    if not cleaned:
        watermark = Image.new("RGBA", image.size, (0, 0, 0, 0))
        watermark_draw = ImageDraw.Draw(watermark, "RGBA")
        watermark_draw.text(xy(150, 360), "DEMO WATERMARK", fill=(220, 30, 30, 78), font=watermark_font)
        watermark = watermark.rotate(32, resample=Image.Resampling.BICUBIC, center=xy(306, 396))
        image = Image.alpha_composite(image.convert("RGBA"), watermark).convert("RGB")
        draw = ImageDraw.Draw(image, "RGBA")
        draw.rounded_rectangle(box((406, 646, 542, 700)), radius=8 * scale, fill="#fff7f5", outline="#db3326", width=3 * scale)
        draw.text(xy(424, 666), "SIGNED DEMO", fill="#db3326", font=stamp_font)
        badge_fill = "#fff1f0"
        badge_text = "#b42318"
        badge = "Before cleanup"
    else:
        badge_fill = "#ecfdf3"
        badge_text = "#027a48"
        badge = "After cleanup"

    draw.rounded_rectangle(box((72, 58, 212, 90)), radius=6 * scale, fill=badge_fill, outline=badge_text, width=1 * scale)
    draw.text(xy(86, 65), badge, fill=badge_text, font=small_font)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.resize((612, 792), Image.Resampling.LANCZOS).save(path, optimize=True)


def create_comparison_png() -> None:
    from PIL import Image, ImageDraw, ImageFont

    before = Image.open(BEFORE_PNG).convert("RGB")
    after = Image.open(AFTER_PNG).convert("RGB")
    gap = 28
    margin = 28
    title_height = 58
    canvas = Image.new("RGB", (before.width * 2 + gap + margin * 2, before.height + title_height + margin * 2), "#f2f4f7")
    draw = ImageDraw.Draw(canvas)
    title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
    label_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    draw.text((margin, 22), "PDF Clean: before and after", fill="#151719", font=title_font)
    left_x = margin
    right_x = margin + before.width + gap
    top = margin + title_height
    canvas.paste(before, (left_x, top))
    canvas.paste(after, (right_x, top))
    draw.text((left_x, top - 28), "Before: watermark and signature widget", fill="#b42318", font=label_font)
    draw.text((right_x, top - 28), "After: cleaned text PDF", fill="#027a48", font=label_font)
    COMPARISON_PNG.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(COMPARISON_PNG, optimize=True)


def main() -> int:
    create_demo_pdf(INPUT_PDF)
    report = clean_pdf(INPUT_PDF, CLEAN_PDF)
    report.input = str(INPUT_PDF.relative_to(ROOT))
    report.output = str(CLEAN_PDF.relative_to(ROOT))
    write_report(report, REPORT_JSON)
    create_preview_png(BEFORE_PNG, cleaned=False)
    create_preview_png(AFTER_PNG, cleaned=True)
    create_comparison_png()

    reader = PdfReader(str(CLEAN_PDF), strict=False)
    if len(reader.pages) != 1:
        raise SystemExit("Demo clean output should keep one page.")
    if report.signature_fields_removed != 1 or report.signature_widgets_removed != 1:
        raise SystemExit("Demo cleanup did not remove the synthetic signature structures.")
    print(f"Wrote {INPUT_PDF.relative_to(ROOT)}")
    print(f"Wrote {CLEAN_PDF.relative_to(ROOT)}")
    print(f"Wrote {REPORT_JSON.relative_to(ROOT)}")
    print(f"Wrote {BEFORE_PNG.relative_to(ROOT)}")
    print(f"Wrote {AFTER_PNG.relative_to(ROOT)}")
    print(f"Wrote {COMPARISON_PNG.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
