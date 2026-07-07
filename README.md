# PDF Watermark Remover

[![CI](https://github.com/QVQZZH/pdf-watermark-remover/actions/workflows/ci.yml/badge.svg)](https://github.com/QVQZZH/pdf-watermark-remover/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white&style=flat-square)](https://www.python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-ready-009688?logo=fastapi&logoColor=white&style=flat-square)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](https://github.com/QVQZZH/pdf-watermark-remover/pulls)

[Quick Start](#quick-start) · [Features](#features) · [CLI](#cli) · [API](#api) · [Limits](#current-limits) · [Roadmap](#roadmap) · **English** | [中文](README.zh-CN.md)

**Remove watermarks, signature widgets, stamp-like overlays, and visual obstructions from text-based PDFs while preserving the original text layer whenever possible.**

PDF Watermark Remover is a local-first tool for cleaning text-based business documents, statements, forms, and records. It rewrites PDFs with `pypdf`, removes common digital signature artifacts, detects image or transparent-text overlays over text, and provides both a command-line interface and a small FastAPI web UI.

The project is designed for privacy-sensitive workflows: files are processed locally, uploaded PDFs are not included in this repository, and generated outputs are ignored by Git.

## Demo Files

The repository includes a synthetic, privacy-safe sample that demonstrates the cleanup flow:

![PDF Watermark Remover before and after comparison](https://raw.githubusercontent.com/QVQZZH/pdf-watermark-remover/main/docs/examples/demo-comparison.png)

- [Before preview PNG](docs/examples/demo-before.png)
- [After preview PNG](docs/examples/demo-after.png)
- [Input PDF with demo watermark and signature widget](docs/examples/demo-statement.pdf)
- [Cleaned PDF output](docs/examples/demo-statement-clean.pdf)
- [JSON cleanup report](docs/examples/demo-report.json)

The sample report removes one signature field, one signature widget, and one transparent-text watermark while preserving the text layer:

```json
{
  "signature_fields_removed": 1,
  "signature_widgets_removed": 1,
  "transparent_text_blocks_removed": 1,
  "text_length_before": 581,
  "text_length_after": 566
}
```

Regenerate these demo files with:

```bash
python scripts/create_demo_examples.py
```

## Keywords

`PDF signature removal` · `PDF watermark cleanup` · `text PDF cleaner` · `FastAPI PDF tool` · `pypdf signature widget remover` · `PDF AcroForm signature field cleanup` · `local PDF processing`

## Features

- Remove PDF signature Widget annotations.
- Remove AcroForm signature fields and signature flags.
- Preserve page count, layout, and extractable text layer where possible.
- Detect image XObjects that overlap text and remove detected image obstructions by default.
- Detect low-transparency text watermarks and transparent Form XObject watermarks.
- Optionally remove all image XObjects for aggressive cleanup.
- Optionally apply manual whiteout rectangles from the CLI.
- Generate JSON reports with page-level findings, removed counts, warnings, and obstruction summaries.
- Use a browser upload UI for analysis, cleanup, and obstruction preview images.

## Use Cases

- Clean text-based PDF statements before internal review.
- Remove empty or visible digital signature widgets from forms.
- Identify image stamps, transparent watermark text, or overlay artifacts that cover text.
- Produce a report that documents what changed during cleanup.
- Run local PDF processing without sending documents to a hosted service.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the web app:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## CLI

Clean a PDF and write a JSON report:

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --report output/report.json
```

Apply a manual white rectangle in PDF coordinates:

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --whiteout 50,680,170,772
```

Aggressively remove every image XObject:

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --remove-images
```

Keep detected image or transparent-text obstructions and only clean signature structures:

```bash
python -m app.pdf_tools input.pdf output/clean.pdf --keep-detected-obstructions
```

## API

### Analyze PDF

```http
POST /api/analyze
Content-Type: multipart/form-data
```

Form field:

```text
file=<PDF file>
```

Returns a JSON `PdfReport` with page count, text length, signature-field counts, detected obstruction candidates, and summary text.

### Clean PDF

```http
POST /api/clean
Content-Type: multipart/form-data
```

Form fields:

```text
file=<PDF file>
remove_detected_obstructions=true
remove_images=false
```

Returns the cleaned PDF. Response headers include:

```text
X-Report-Id
X-Image-Xobjects-Removed
X-Transparent-Text-Blocks-Removed
X-Obstruction-Count
```

## Requirements

- Python 3.10+
- `pypdf`
- `FastAPI`
- `uvicorn`
- `python-multipart`
- `Pillow` for image preview generation in the web analyzer

## How It Works

```text
PDF input
  -> pypdf reads pages, annotations, AcroForm fields, resources, and content streams
  -> signature widgets and signature fields are removed
  -> likely image and transparent-text obstructions are detected against text boxes
  -> detected obstructions can be removed from page resources and content operations
  -> optional whiteout rectangles can be appended
  -> the document is rewritten as a new PDF
  -> a JSON report records changes, warnings, and page-level findings
```

## Project Structure

```text
app/
  main.py        FastAPI app and browser upload endpoints
  pdf_tools.py   PDF analysis, cleanup, reporting, and CLI
web/
  index.html     Browser UI
  script.js      Upload, analyze, clean, and preview interactions
  style.css      UI styles
test/
  test_pdf_tools.py
```

## Current Limits

- Encrypted PDFs are rejected.
- Scanned image-only PDFs are not OCR processed.
- Image removal can also remove logos, scanned page backgrounds, or other useful imagery.
- Automatic obstruction detection is heuristic and should be checked on important documents.
- The tool does not repair damaged PDFs or bypass document access restrictions.

## Development

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s test
python -m uvicorn app.main:app --reload
```

## Roadmap

- Add before/after page preview comparison.
- Add interactive rectangle selection for manual whiteout in the browser.
- Add batch processing and ZIP export.
- Add Docker packaging.
- Add more synthetic fixtures for transparent text and image obstruction detection.

## FAQ

### Does PDF Watermark Remover upload files to a remote service?

No. The app runs locally. Uploaded files go to the local FastAPI process, and generated outputs are written under `output/`.

### Does it work on scanned PDFs?

It can rewrite scanned PDFs, but it does not perform OCR. The strongest results are on text-based PDFs with an extractable text layer.

### Can it remove all watermarks?

No. PDF watermark implementations vary. PDF Watermark Remover handles signature structures, some image overlays, and low-transparency text or Form XObject watermarks. Manual whiteout can be used as a fallback.

### Is it safe to use on original files?

The cleaner writes a new output file and does not modify the input path. Still, keep backups for important documents.

## License

MIT
