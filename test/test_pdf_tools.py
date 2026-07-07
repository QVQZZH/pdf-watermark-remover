from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, RectangleObject, TextStringObject

from app.pdf_tools import analyze_pdf, clean_pdf, write_report
from scripts.create_demo_examples import CLEAN_PDF, INPUT_PDF, REPORT_JSON, main as create_demo_examples


def create_signature_pdf(path: Path) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)

    signature_field = DictionaryObject(
        {
            NameObject("/FT"): NameObject("/Sig"),
            NameObject("/T"): TextStringObject("ApprovalSignature"),
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/Rect"): RectangleObject([20, 20, 160, 60]),
            NameObject("/F"): NumberObject(4),
            NameObject("/P"): page.indirect_reference,
        }
    )
    signature_ref = writer._add_object(signature_field)
    page[NameObject("/Annots")] = ArrayObject([signature_ref])
    writer._root_object[NameObject("/AcroForm")] = DictionaryObject(
        {
            NameObject("/Fields"): ArrayObject([signature_ref]),
            NameObject("/SigFlags"): NumberObject(3),
        }
    )

    with path.open("wb") as handle:
        writer.write(handle)


class PdfToolsTest(unittest.TestCase):
    def test_clean_pdf_removes_signature_structures(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "signed.pdf"
            output_path = root / "clean.pdf"
            report_path = root / "report.json"
            create_signature_pdf(input_path)

            before = analyze_pdf(input_path)
            report = clean_pdf(input_path, output_path)
            write_report(report, report_path)
            after = analyze_pdf(output_path)

            self.assertEqual(before.pages, 1)
            self.assertEqual(after.pages, 1)
            self.assertEqual(before.signature_fields_before, 1)
            self.assertEqual(report.signature_fields_removed, 1)
            self.assertEqual(report.signature_widgets_removed, 1)
            self.assertEqual(after.signature_fields_before, 0)
            self.assertFalse(after.acroform_present_before)
            self.assertTrue(output_path.exists())
            self.assertTrue(report_path.exists())

            reader = PdfReader(str(output_path), strict=False)
            self.assertNotIn("/Annots", reader.pages[0])

    def test_demo_examples_are_regenerated(self) -> None:
        create_demo_examples()
        report = analyze_pdf(INPUT_PDF)
        clean_report = clean_pdf(INPUT_PDF, CLEAN_PDF)

        self.assertEqual(report.pages, 1)
        self.assertEqual(clean_report.signature_fields_removed, 1)
        self.assertEqual(clean_report.signature_widgets_removed, 1)
        self.assertEqual(clean_report.transparent_text_blocks_removed, 1)
        self.assertTrue(INPUT_PDF.exists())
        self.assertTrue(CLEAN_PDF.exists())
        self.assertTrue(REPORT_JSON.exists())


if __name__ == "__main__":
    unittest.main()
