from __future__ import annotations

import tempfile
import uuid
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.pdf_tools import analyze_pdf, clean_pdf, write_report


ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
OUTPUT_DIR = ROOT / "output"
PREVIEW_DIR = OUTPUT_DIR / "previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PDF Watermark Remover", version="0.1.0")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
app.mount("/previews", StaticFiles(directory=PREVIEW_DIR), name="previews")


def image_average_hash(image: object, *, size: int = 8) -> int:
    from PIL import Image

    grayscale = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    pixels = list(grayscale.getdata())
    average = sum(pixels) / len(pixels)
    value = 0
    for index, pixel in enumerate(pixels):
        if pixel >= average:
            value |= 1 << index
    return value


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def add_obstruction_previews(pdf_path: Path, report: object, *, max_previews: int = 12) -> None:
    try:
        from pypdf import PdfReader
    except Exception:
        return

    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        reader = PdfReader(str(pdf_path), strict=False)
    except Exception:
        return

    created = 0
    preview_by_digest: dict[str, str] = {}
    perceptual_previews: list[tuple[tuple[int | None, int | None], int, str]] = []
    for page_report in report.page_reports:
        if page_report.page_index >= len(reader.pages):
            continue
        page = reader.pages[page_report.page_index]
        for candidate in page_report.obstruction_candidates:
            if candidate.kind != "image":
                continue
            try:
                image = page.images[candidate.name]
                digest = sha256(image.data).hexdigest()
                if digest in preview_by_digest:
                    candidate.preview_url = preview_by_digest[digest]
                    continue

                perceptual_hash = image_average_hash(image.image)
                image_size = (candidate.width, candidate.height)
                similar_url = next(
                    (
                        url
                        for existing_size, existing_hash, url in perceptual_previews
                        if existing_size == image_size and hamming_distance(existing_hash, perceptual_hash) <= 8
                    ),
                    None,
                )
                if similar_url:
                    preview_by_digest[digest] = similar_url
                else:
                    if created >= max_previews:
                        continue
                    filename = f"{uuid.uuid4().hex}.png"
                    target = PREVIEW_DIR / filename
                    image.image.save(target)
                    preview_by_digest[digest] = f"/previews/{filename}"
                    perceptual_previews.append((image_size, perceptual_hash, preview_by_digest[digest]))
                    created += 1
            except Exception:
                continue
            candidate.preview_url = preview_by_digest[digest]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (WEB_DIR / "index.html").read_text(encoding="utf-8")


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "input.pdf"
        input_path.write_bytes(await file.read())
        report = analyze_pdf(input_path)
        add_obstruction_previews(input_path, report)
        return asdict(report)


@app.post("/api/clean")
async def clean(
    file: UploadFile = File(...),
    remove_images: bool = Form(False),
    remove_detected_obstructions: bool = Form(True),
) -> FileResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    job_id = uuid.uuid4().hex
    output_path = OUTPUT_DIR / f"{Path(file.filename).stem}_{job_id}_clean.pdf"
    report_path = OUTPUT_DIR / f"{Path(file.filename).stem}_{job_id}_report.json"

    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "input.pdf"
        input_path.write_bytes(await file.read())
        try:
            report = clean_pdf(
                input_path,
                output_path,
                remove_detected_obstructions=remove_detected_obstructions,
                remove_images=remove_images,
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        write_report(report, report_path)

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=f"{Path(file.filename).stem}_clean.pdf",
        headers={
            "X-Report-Id": job_id,
            "X-Image-Xobjects-Removed": str(report.image_xobjects_removed),
            "X-Transparent-Text-Blocks-Removed": str(report.transparent_text_blocks_removed),
            "X-Obstruction-Count": str(report.obstruction_summary.obstruction_count),
        },
    )
