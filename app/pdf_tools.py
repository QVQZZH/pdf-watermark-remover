from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DictionaryObject,
    FloatObject,
    IndirectObject,
    NameObject,
    NumberObject,
)


SIGNATURE_FIELD = "/Sig"
SIGNATURE_WIDGET = "/Widget"
OVERLAP_THRESHOLD = 0.08
TRANSPARENT_WATERMARK_ALPHA = 0.45
FORM_WATERMARK_MIN_PAGE_RATIO = 0.01
FORM_WATERMARK_LARGE_PAGE_RATIO = 0.08
TEXT_SHOW_OPERATORS = {b"Tj", b"TJ", b"'", b'"'}


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return max(0.0, self.x1 - self.x0)

    @property
    def height(self) -> float:
        return max(0.0, self.y1 - self.y0)

    @property
    def area(self) -> float:
        return self.width * self.height

    def intersection_area(self, other: "Rect") -> float:
        x0 = max(self.x0, other.x0)
        y0 = max(self.y0, other.y0)
        x1 = min(self.x1, other.x1)
        y1 = min(self.y1, other.y1)
        return max(0.0, x1 - x0) * max(0.0, y1 - y0)

    def as_list(self) -> list[float]:
        return [round(self.x0, 3), round(self.y0, 3), round(self.x1, 3), round(self.y1, 3)]


@dataclass
class ObstructionCandidate:
    kind: str
    name: str
    rect: list[float]
    width: int | None = None
    height: int | None = None
    overlap_text_chars: int = 0
    overlap_ratio: float = 0.0
    reason: str = ""
    preview_url: str | None = None


@dataclass
class ObstructionSummary:
    has_obstruction: bool = False
    obstruction_count: int = 0
    image_obstruction_count: int = 0
    transparent_text_obstruction_count: int = 0
    signature_widget_count: int = 0
    signature_field_count: int = 0
    pages_with_obstruction: int = 0
    message: str = ""


@dataclass
class PageReport:
    page_index: int
    annotations_before: int = 0
    annotations_after: int = 0
    signature_widgets_removed: int = 0
    text_length: int = 0
    xobjects: dict[str, int] = field(default_factory=dict)
    text_boxes: int = 0
    obstruction_candidates: list[ObstructionCandidate] = field(default_factory=list)


@dataclass
class PdfReport:
    input: str
    output: str | None
    pages: int
    encrypted: bool
    text_length_before: int = 0
    text_length_after: int = 0
    acroform_present_before: bool = False
    acroform_present_after: bool = False
    signature_fields_before: int = 0
    signature_fields_after: int = 0
    signature_fields_removed: int = 0
    signature_widgets_removed: int = 0
    image_xobjects_removed: int = 0
    transparent_text_blocks_removed: int = 0
    whiteout_regions_applied: int = 0
    obstruction_summary: ObstructionSummary = field(default_factory=ObstructionSummary)
    page_reports: list[PageReport] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FormInvocation:
    name: NameObject
    operation_index: int
    rect: Rect
    alpha: float
    overlap_text_chars: int
    overlap_ratio: float
    page_ratio: float
    marked_watermark: bool


def resolve(value: Any) -> Any:
    if isinstance(value, IndirectObject):
        return value.get_object()
    return value


def is_signature_widget(annotation: Any) -> bool:
    annot = resolve(annotation)
    if not isinstance(annot, DictionaryObject):
        return False
    if annot.get("/Subtype") != SIGNATURE_WIDGET:
        return False
    if annot.get("/FT") == SIGNATURE_FIELD:
        return True
    parent = resolve(annot.get("/Parent"))
    return isinstance(parent, DictionaryObject) and parent.get("/FT") == SIGNATURE_FIELD


def is_signature_field(field: Any) -> bool:
    field_obj = resolve(field)
    return isinstance(field_obj, DictionaryObject) and field_obj.get("/FT") == SIGNATURE_FIELD


def count_signature_fields(reader: PdfReader) -> int:
    root = resolve(reader.trailer.get("/Root", {}))
    if not isinstance(root, DictionaryObject):
        return 0
    acroform = resolve(root.get("/AcroForm"))
    if not isinstance(acroform, DictionaryObject):
        return 0
    fields = resolve(acroform.get("/Fields", []))
    if not isinstance(fields, Iterable):
        return 0
    return sum(1 for field in fields if is_signature_field(field))


def text_length(reader: PdfReader) -> int:
    total = 0
    for page in reader.pages:
        try:
            total += len(page.extract_text() or "")
        except Exception:
            continue
    return total


def multiply_matrix(left: list[float], right: list[float]) -> list[float]:
    a, b, c, d, e, f = left
    g, h, i, j, k, l = right
    return [
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * l + e,
        b * k + d * l + f,
    ]


def transform_point(matrix: list[float], x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f


def rect_from_matrix(matrix: list[float]) -> Rect:
    points = [
        transform_point(matrix, 0, 0),
        transform_point(matrix, 1, 0),
        transform_point(matrix, 0, 1),
        transform_point(matrix, 1, 1),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return Rect(min(xs), min(ys), max(xs), max(ys))


def rect_from_bbox(matrix: list[float], bbox: Any) -> Rect | None:
    if not isinstance(bbox, Iterable):
        return None
    try:
        x0, y0, x1, y1 = [float(value) for value in bbox]
    except Exception:
        return None
    points = [
        transform_point(matrix, x0, y0),
        transform_point(matrix, x1, y0),
        transform_point(matrix, x0, y1),
        transform_point(matrix, x1, y1),
    ]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return Rect(min(xs), min(ys), max(xs), max(ys))


def rect_text_overlap(rect: Rect, text_boxes: list[tuple[Rect, int]]) -> tuple[int, float]:
    overlap_chars = 0
    overlap_area = 0.0
    for text_rect, text_len in text_boxes:
        area = rect.intersection_area(text_rect)
        if area <= 0:
            continue
        overlap_area += area
        overlap_chars += text_len
    overlap_ratio = min(1.0, overlap_area / rect.area) if rect.area else 0.0
    return overlap_chars, overlap_ratio


def matrix_from_pdf(value: Any) -> list[float]:
    if not isinstance(value, Iterable):
        return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    try:
        values = [float(item) for item in value]
    except Exception:
        return [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    return values if len(values) == 6 else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]


def collect_text_boxes(page: Any) -> list[tuple[Rect, int]]:
    boxes: list[tuple[Rect, int]] = []

    def visitor(text: str, cm: Any, tm: Any, font_dict: Any, font_size: Any) -> None:
        normalized = "".join(text.split())
        if not normalized:
            return
        try:
            matrix = multiply_matrix([float(value) for value in cm], [float(value) for value in tm])
            size = float(font_size or 10)
        except Exception:
            return
        x, y = transform_point(matrix, 0, 0)
        width = max(size * 0.45 * len(normalized), size)
        height = max(size * 1.25, 1.0)
        boxes.append((Rect(x, y - size * 0.25, x + width, y + height), len(normalized)))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []
    return boxes


def count_page_xobjects(page: Any) -> dict[str, int]:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return {}
    xobjects = resolve(resources.get("/XObject", {}))
    if not isinstance(xobjects, DictionaryObject):
        return {}
    counts: dict[str, int] = {}
    for value in xobjects.values():
        obj = resolve(value)
        subtype = str(obj.get("/Subtype")) if isinstance(obj, DictionaryObject) else "unknown"
        counts[subtype] = counts.get(subtype, 0) + 1
    return counts


def image_xobject_names(page: Any) -> set[NameObject]:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return set()
    xobjects = resolve(resources.get("/XObject", {}))
    if not isinstance(xobjects, DictionaryObject):
        return set()

    names: set[NameObject] = set()
    for name, value in xobjects.items():
        obj = resolve(value)
        if isinstance(obj, DictionaryObject) and obj.get("/Subtype") == NameObject("/Image"):
            names.add(NameObject(name))
    return names


def form_xobjects(page: Any) -> dict[NameObject, DictionaryObject]:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return {}
    xobjects = resolve(resources.get("/XObject", {}))
    if not isinstance(xobjects, DictionaryObject):
        return {}

    forms: dict[NameObject, DictionaryObject] = {}
    for name, value in xobjects.items():
        obj = resolve(value)
        if isinstance(obj, DictionaryObject) and obj.get("/Subtype") == NameObject("/Form"):
            forms[NameObject(name)] = obj
    return forms


def get_xobject_size(page: Any, name: NameObject) -> tuple[int | None, int | None]:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return None, None
    xobjects = resolve(resources.get("/XObject", {}))
    if not isinstance(xobjects, DictionaryObject) or name not in xobjects:
        return None, None
    obj = resolve(xobjects[name])
    if not isinstance(obj, DictionaryObject):
        return None, None
    width = obj.get("/Width")
    height = obj.get("/Height")
    return int(width) if width is not None else None, int(height) if height is not None else None


def transparent_extgstates(page: Any, threshold: float = TRANSPARENT_WATERMARK_ALPHA) -> dict[NameObject, float]:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return {}
    states = resolve(resources.get("/ExtGState", {}))
    if not isinstance(states, DictionaryObject):
        return {}

    transparent: dict[NameObject, float] = {}
    for name, value in states.items():
        state = resolve(value)
        if not isinstance(state, DictionaryObject):
            continue
        alphas = []
        for key in ("/ca", "/CA"):
            alpha = state.get(key)
            if alpha is not None:
                try:
                    alphas.append(float(alpha))
                except Exception:
                    pass
        if alphas and min(alphas) <= threshold:
            transparent[NameObject(name)] = min(alphas)
    return transparent


def extgstate_alpha(resources: Any, state_name: NameObject) -> float | None:
    if not isinstance(resources, DictionaryObject):
        return None
    states = resolve(resources.get("/ExtGState", {}))
    if not isinstance(states, DictionaryObject) or state_name not in states:
        return None
    state = resolve(states[state_name])
    if not isinstance(state, DictionaryObject):
        return None
    alphas: list[float] = []
    for key in ("/ca", "/CA"):
        alpha = state.get(key)
        if alpha is None:
            continue
        try:
            alphas.append(float(alpha))
        except Exception:
            pass
    return min(alphas) if alphas else None


def form_text_profile(form: DictionaryObject, pdf: PdfReader) -> tuple[bool, float | None]:
    try:
        operations = ContentStream(form, pdf).operations
    except Exception:
        return False, None

    resources = resolve(form.get("/Resources", {}))
    transparent_states = transparent_extgstates(form)
    saw_text = False
    min_alpha: float | None = None
    for operands, operator in operations:
        if operator in TEXT_SHOW_OPERATORS:
            saw_text = True
        elif operator == b"Do":
            return False, None
        elif operator == b"gs" and operands:
            state_name = NameObject(operands[0])
            if state_name in transparent_states:
                alpha = transparent_states[state_name]
            else:
                alpha = extgstate_alpha(resources, state_name)
            if alpha is not None:
                min_alpha = alpha if min_alpha is None else min(min_alpha, alpha)

    return saw_text, min_alpha


def _is_transparent_text_block(operations: list[tuple[Any, Any]], start: int, end: int) -> bool:
    has_text = False
    for operands, operator in operations[start:end]:
        if operator in TEXT_SHOW_OPERATORS:
            has_text = True
        if operator == b"Do":
            return False
    return has_text


def detect_transparent_text_obstructions(page: Any, pdf: PdfReader) -> list[ObstructionCandidate]:
    states = transparent_extgstates(page)
    if not states:
        return []
    contents = page.get("/Contents")
    if not contents:
        return []
    try:
        operations = ContentStream(contents, pdf).operations
    except Exception:
        return []

    candidates: list[ObstructionCandidate] = []
    for index, (operands, operator) in enumerate(operations):
        if operator != b"gs" or not operands:
            continue
        state_name = NameObject(operands[0])
        if state_name not in states:
            continue

        start = index
        depth = 0
        for cursor in range(index - 1, -1, -1):
            op = operations[cursor][1]
            if op == b"Q":
                depth += 1
            elif op == b"q":
                if depth == 0:
                    start = cursor
                    break
                depth -= 1

        end = len(operations)
        depth = 0
        for cursor in range(index + 1, len(operations)):
            op = operations[cursor][1]
            if op == b"q":
                depth += 1
            elif op == b"Q":
                if depth == 0:
                    end = cursor + 1
                    break
                depth -= 1

        if not _is_transparent_text_block(operations, start, end):
            continue

        candidates.append(
            ObstructionCandidate(
                kind="transparent_text",
                name=str(state_name),
                rect=[],
                overlap_text_chars=0,
                overlap_ratio=0.0,
                reason=f"低透明度文字内容流，alpha={states[state_name]:.2f}，可能是斜向水印或浅色遮挡文字。",
            )
        )
    return candidates


def _marked_content_is_watermark(operands: Any) -> bool:
    if not operands or len(operands) < 2:
        return False
    properties = resolve(operands[1])
    if not isinstance(properties, DictionaryObject):
        return False
    values = {str(properties.get("/Subtype", "")), str(properties.get("/Type", ""))}
    return "/Watermark" in values


def transparent_text_form_invocations(
    page: Any, pdf: PdfReader, text_boxes: list[tuple[Rect, int]]
) -> list[FormInvocation]:
    forms = form_xobjects(page)
    if not forms:
        return []
    contents = page.get("/Contents")
    if not contents:
        return []

    try:
        content_stream = ContentStream(contents, pdf)
    except Exception:
        return []

    page_resources = resolve(page.get("/Resources", {}))
    page_area = float(page.mediabox.width) * float(page.mediabox.height)
    stack: list[tuple[list[float], float | None, list[bool]]] = []
    ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    alpha: float | None = None
    marked_stack: list[bool] = []
    potentials: list[FormInvocation] = []
    form_profiles: dict[NameObject, tuple[bool, float | None]] = {}

    for index, (operands, operator) in enumerate(content_stream.operations):
        if operator == b"q":
            stack.append((ctm.copy(), alpha, marked_stack.copy()))
            continue
        if operator == b"Q":
            ctm, alpha, marked_stack = (
                stack.pop() if stack else ([1.0, 0.0, 0.0, 1.0, 0.0, 0.0], None, [])
            )
            continue
        if operator == b"BDC":
            marked_stack.append(_marked_content_is_watermark(operands))
            continue
        if operator == b"EMC":
            if marked_stack:
                marked_stack.pop()
            continue
        if operator == b"gs" and operands:
            current_alpha = extgstate_alpha(page_resources, NameObject(operands[0]))
            if current_alpha is not None:
                alpha = current_alpha
            continue
        if operator == b"cm" and len(operands) == 6:
            try:
                ctm = multiply_matrix(ctm, [float(value) for value in operands])
            except Exception:
                pass
            continue
        if operator != b"Do" or not operands:
            continue

        name = NameObject(operands[0])
        form = forms.get(name)
        if form is None:
            continue

        if name not in form_profiles:
            form_profiles[name] = form_text_profile(form, pdf)
        has_text, form_alpha = form_profiles[name]
        if not has_text:
            continue

        effective_alpha = min(value for value in (alpha, form_alpha) if value is not None) if (
            alpha is not None or form_alpha is not None
        ) else None
        if effective_alpha is None or effective_alpha > TRANSPARENT_WATERMARK_ALPHA:
            continue

        form_matrix = matrix_from_pdf(form.get("/Matrix"))
        rect = rect_from_bbox(multiply_matrix(ctm, form_matrix), form.get("/BBox"))
        if rect is None or rect.area <= 0:
            continue

        overlap_chars, overlap_ratio = rect_text_overlap(rect, text_boxes)
        page_ratio = rect.area / page_area if page_area else 0.0
        marked_watermark = any(marked_stack)
        potentials.append(
            FormInvocation(
                name=name,
                operation_index=index,
                rect=rect,
                alpha=effective_alpha,
                overlap_text_chars=overlap_chars,
                overlap_ratio=overlap_ratio,
                page_ratio=page_ratio,
                marked_watermark=marked_watermark,
            )
        )

    name_counts: dict[NameObject, int] = {}
    for invocation in potentials:
        name_counts[invocation.name] = name_counts.get(invocation.name, 0) + 1

    invocations: list[FormInvocation] = []
    for invocation in potentials:
        is_repeated = name_counts[invocation.name] > 1
        overlaps_page_text = invocation.overlap_text_chars > 0
        meaningful_size = invocation.page_ratio >= FORM_WATERMARK_MIN_PAGE_RATIO
        large_form = invocation.page_ratio >= FORM_WATERMARK_LARGE_PAGE_RATIO
        is_obstruction = invocation.marked_watermark or (
            overlaps_page_text
            and meaningful_size
            and (is_repeated or large_form)
            and (invocation.overlap_ratio >= OVERLAP_THRESHOLD or invocation.page_ratio < 0.65)
        )
        if is_obstruction:
            invocations.append(invocation)
    return invocations


def detect_transparent_text_form_obstructions(
    page: Any, pdf: PdfReader, text_boxes: list[tuple[Rect, int]]
) -> list[ObstructionCandidate]:
    candidates: list[ObstructionCandidate] = []
    for invocation in transparent_text_form_invocations(page, pdf, text_boxes):
        reason = (
            f"低透明度 Form XObject 文字，alpha={invocation.alpha:.2f}，"
            "可能是重复平铺或斜向文字水印。"
        )
        if invocation.marked_watermark:
            reason += " PDF 内容标记为 Watermark。"
        candidates.append(
            ObstructionCandidate(
                kind="transparent_text",
                name=str(invocation.name),
                rect=invocation.rect.as_list(),
                overlap_text_chars=invocation.overlap_text_chars,
                overlap_ratio=round(invocation.overlap_ratio, 4),
                reason=reason,
            )
        )
    return candidates


def detect_image_obstructions(page: Any, pdf: PdfReader, text_boxes: list[tuple[Rect, int]]) -> list[ObstructionCandidate]:
    image_names = image_xobject_names(page)
    if not image_names:
        return []

    candidates: list[ObstructionCandidate] = []
    contents = page.get("/Contents")
    if not contents:
        return candidates

    stack: list[list[float]] = []
    ctm = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    try:
        content_stream = ContentStream(contents, pdf)
    except Exception:
        return candidates

    for operands, operator in content_stream.operations:
        if operator == b"q":
            stack.append(ctm.copy())
            continue
        if operator == b"Q":
            ctm = stack.pop() if stack else [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
            continue
        if operator == b"cm" and len(operands) == 6:
            try:
                ctm = multiply_matrix(ctm, [float(value) for value in operands])
            except Exception:
                pass
            continue
        if operator != b"Do" or not operands:
            continue

        name = NameObject(operands[0])
        if name not in image_names:
            continue

        rect = rect_from_matrix(ctm)
        if rect.area <= 0:
            continue
        overlap_chars = 0
        overlap_area = 0.0
        for text_rect, text_len in text_boxes:
            area = rect.intersection_area(text_rect)
            if area <= 0:
                continue
            overlap_area += area
            overlap_chars += text_len
        overlap_ratio = min(1.0, overlap_area / rect.area) if rect.area else 0.0
        page_area = float(page.mediabox.width) * float(page.mediabox.height)
        page_ratio = rect.area / page_area if page_area else 0.0
        is_obstruction = overlap_chars > 0 and (overlap_ratio >= OVERLAP_THRESHOLD or page_ratio < 0.35)
        if not is_obstruction:
            continue
        width, height = get_xobject_size(page, name)
        candidates.append(
            ObstructionCandidate(
                kind="image",
                name=str(name),
                rect=rect.as_list(),
                width=width,
                height=height,
                overlap_text_chars=overlap_chars,
                overlap_ratio=round(overlap_ratio, 4),
                reason="图片对象覆盖了文字区域，可能是印章、水印、签名图片或遮挡层。",
            )
        )
    return candidates


def summarize_obstructions(report: PdfReport) -> None:
    image_count = sum(
        1 for page in report.page_reports for candidate in page.obstruction_candidates if candidate.kind == "image"
    )
    transparent_text_count = sum(
        1
        for page in report.page_reports
        for candidate in page.obstruction_candidates
        if candidate.kind == "transparent_text"
    )
    signature_count = report.signature_widgets_removed or report.signature_fields_before
    pages = sum(1 for page in report.page_reports if page.obstruction_candidates or page.signature_widgets_removed)
    total = image_count + transparent_text_count + signature_count
    report.obstruction_summary = ObstructionSummary(
        has_obstruction=total > 0,
        obstruction_count=total,
        image_obstruction_count=image_count,
        transparent_text_obstruction_count=transparent_text_count,
        signature_widget_count=report.signature_widgets_removed,
        signature_field_count=report.signature_fields_before,
        pages_with_obstruction=pages,
        message=(
            f"检测到 {total} 个疑似遮挡元素，其中图片遮挡 {image_count} 个、透明文字水印 {transparent_text_count} 个、签名控件 {report.signature_widgets_removed} 个、签名字段 {report.signature_fields_before} 个。"
            if total
            else "未检测到明显覆盖文字层的签名、印章、水印或图片遮挡。"
        ),
    )


def analyze_pdf(input_path: str | Path) -> PdfReport:
    path = Path(input_path)
    reader = PdfReader(str(path), strict=False)
    report = PdfReport(
        input=str(path),
        output=None,
        pages=len(reader.pages),
        encrypted=reader.is_encrypted,
        acroform_present_before=bool(resolve(reader.trailer.get("/Root", {})).get("/AcroForm")),
        signature_fields_before=count_signature_fields(reader),
    )
    report.text_length_before = text_length(reader)
    report.text_length_after = report.text_length_before
    report.signature_fields_after = report.signature_fields_before
    report.acroform_present_after = report.acroform_present_before

    for index, page in enumerate(reader.pages):
        annotations = resolve(page.get("/Annots", [])) or []
        if not isinstance(annotations, Iterable):
            annotations = []
        text_boxes = collect_text_boxes(page)
        obstruction_candidates = detect_image_obstructions(page, reader, text_boxes)
        obstruction_candidates.extend(detect_transparent_text_obstructions(page, reader))
        obstruction_candidates.extend(detect_transparent_text_form_obstructions(page, reader, text_boxes))
        try:
            page_text_len = len(page.extract_text() or "")
        except Exception:
            page_text_len = 0
        signature_widgets = sum(1 for annotation in annotations if is_signature_widget(annotation))
        report.page_reports.append(
            PageReport(
                page_index=index,
                annotations_before=len(list(annotations)),
                annotations_after=len(list(annotations)),
                signature_widgets_removed=signature_widgets,
                text_length=page_text_len,
                text_boxes=len(text_boxes),
                xobjects=count_page_xobjects(page),
                obstruction_candidates=obstruction_candidates,
            )
        )
        report.signature_widgets_removed += signature_widgets
    summarize_obstructions(report)
    return report


def _clean_page_annotations(page: Any, page_report: PageReport) -> None:
    annotations = resolve(page.get("/Annots", []))
    if not annotations:
        page_report.annotations_before = 0
        page_report.annotations_after = 0
        return

    kept = ArrayObject()
    removed = 0
    for annotation in annotations:
        if is_signature_widget(annotation):
            removed += 1
            continue
        kept.append(annotation)

    page_report.annotations_before = len(annotations)
    page_report.annotations_after = len(kept)
    page_report.signature_widgets_removed = removed

    if kept:
        page[NameObject("/Annots")] = kept
    elif "/Annots" in page:
        del page["/Annots"]


def _clean_acroform(writer: PdfWriter) -> tuple[int, int, bool]:
    root = writer._root_object
    acroform = resolve(root.get("/AcroForm"))
    if not isinstance(acroform, DictionaryObject):
        return 0, 0, False

    fields = resolve(acroform.get("/Fields", []))
    if not isinstance(fields, Iterable):
        return 0, 0, True

    kept = ArrayObject()
    before = 0
    removed = 0
    for field_obj in fields:
        before += 1
        if is_signature_field(field_obj):
            removed += 1
            continue
        kept.append(field_obj)

    if kept:
        acroform[NameObject("/Fields")] = kept
        if "/SigFlags" in acroform and removed:
            del acroform["/SigFlags"]
        return removed, before - removed, True

    if "/AcroForm" in root:
        del root["/AcroForm"]
    return removed or before, 0, False


def _remove_image_xobjects(page: Any, pdf: PdfReader, names_to_remove: set[NameObject] | None = None) -> int:
    resources = resolve(page.get("/Resources", {}))
    if not isinstance(resources, DictionaryObject):
        return 0
    xobjects = resolve(resources.get("/XObject", {}))
    if not isinstance(xobjects, DictionaryObject):
        return 0

    image_names: set[NameObject] = set()
    for name, value in list(xobjects.items()):
        obj = resolve(value)
        if (
            isinstance(obj, DictionaryObject)
            and obj.get("/Subtype") == NameObject("/Image")
            and (names_to_remove is None or NameObject(name) in names_to_remove)
        ):
            image_names.add(NameObject(name))
            del xobjects[name]

    if not image_names:
        return 0

    if xobjects:
        resources[NameObject("/XObject")] = xobjects
    elif "/XObject" in resources:
        del resources["/XObject"]

    contents = page.get("/Contents")
    if contents:
        content_stream = ContentStream(contents, pdf)
        content_stream.operations = [
            (operands, operator)
            for operands, operator in content_stream.operations
            if not (
                operator == b"Do"
                and operands
                and NameObject(operands[0]) in image_names
            )
        ]
        page[NameObject("/Contents")] = content_stream

    return len(image_names)


def _transparent_text_block_ranges(page: Any, pdf: PdfReader) -> list[tuple[int, int]]:
    states = transparent_extgstates(page)
    if not states:
        return []
    contents = page.get("/Contents")
    if not contents:
        return []
    try:
        operations = ContentStream(contents, pdf).operations
    except Exception:
        return []

    ranges: list[tuple[int, int]] = []
    for index, (operands, operator) in enumerate(operations):
        if operator != b"gs" or not operands or NameObject(operands[0]) not in states:
            continue

        start = index
        depth = 0
        for cursor in range(index - 1, -1, -1):
            op = operations[cursor][1]
            if op == b"Q":
                depth += 1
            elif op == b"q":
                if depth == 0:
                    start = cursor
                    break
                depth -= 1

        end = len(operations)
        depth = 0
        for cursor in range(index + 1, len(operations)):
            op = operations[cursor][1]
            if op == b"q":
                depth += 1
            elif op == b"Q":
                if depth == 0:
                    end = cursor + 1
                    break
                depth -= 1

        if _is_transparent_text_block(operations, start, end):
            ranges.append((start, end))
    return ranges


def _remove_transparent_text_blocks(page: Any, pdf: PdfReader) -> int:
    contents = page.get("/Contents")
    if not contents:
        return 0
    try:
        content_stream = ContentStream(contents, pdf)
    except Exception:
        return 0

    ranges = _transparent_text_block_ranges(page, pdf)
    if not ranges:
        return 0

    remove_indexes: set[int] = set()
    for start, end in ranges:
        remove_indexes.update(range(start, end))
    content_stream.operations = [
        operation for index, operation in enumerate(content_stream.operations) if index not in remove_indexes
    ]
    page[NameObject("/Contents")] = content_stream
    return len(ranges)


def _remove_transparent_text_form_invocations(
    page: Any, pdf: PdfReader, text_boxes: list[tuple[Rect, int]]
) -> int:
    contents = page.get("/Contents")
    if not contents:
        return 0
    try:
        content_stream = ContentStream(contents, pdf)
    except Exception:
        return 0

    invocations = transparent_text_form_invocations(page, pdf, text_boxes)
    if not invocations:
        return 0

    remove_indexes = {invocation.operation_index for invocation in invocations}
    removed_names = {invocation.name for invocation in invocations}
    content_stream.operations = [
        operation for index, operation in enumerate(content_stream.operations) if index not in remove_indexes
    ]
    remaining_names = {
        NameObject(operands[0])
        for operands, operator in content_stream.operations
        if operator == b"Do" and operands
    }
    resources = resolve(page.get("/Resources", {}))
    xobjects = resolve(resources.get("/XObject", {})) if isinstance(resources, DictionaryObject) else None
    if isinstance(xobjects, DictionaryObject):
        for name in removed_names - remaining_names:
            if name in xobjects:
                del xobjects[name]
        if xobjects:
            resources[NameObject("/XObject")] = xobjects
        elif "/XObject" in resources:
            del resources["/XObject"]
    page[NameObject("/Contents")] = content_stream
    return len(remove_indexes)


def _add_whiteout(page: Any, rect: list[float]) -> None:
    # Add a simple white rectangle at the end of the page content stream.
    x0, y0, x1, y1 = rect
    width = x1 - x0
    height = y1 - y0
    stream = f"\nq\n1 1 1 rg\n1 1 1 RG\n{x0:.3f} {y0:.3f} {width:.3f} {height:.3f} re\nf\nQ\n"
    page.merge_page(_single_whiteout_page(page, stream))


def _single_whiteout_page(page: Any, stream: str) -> Any:
    from pypdf import PageObject
    from pypdf.generic import DecodedStreamObject

    media_box = page.mediabox
    overlay = PageObject.create_blank_page(width=float(media_box.width), height=float(media_box.height))
    content = DecodedStreamObject()
    content.set_data(stream.encode("ascii"))
    overlay[NameObject("/Contents")] = content
    return overlay


def clean_pdf(
    input_path: str | Path,
    output_path: str | Path,
    *,
    remove_detected_obstructions: bool = True,
    remove_images: bool = False,
    whiteout_regions: list[list[float]] | None = None,
) -> PdfReport:
    input_path = Path(input_path)
    output_path = Path(output_path)
    reader = PdfReader(str(input_path), strict=False)
    if reader.is_encrypted:
        raise ValueError("Encrypted PDFs are not supported.")

    report = PdfReport(
        input=str(input_path),
        output=str(output_path),
        pages=len(reader.pages),
        encrypted=False,
        acroform_present_before=bool(resolve(reader.trailer.get("/Root", {})).get("/AcroForm")),
        signature_fields_before=count_signature_fields(reader),
    )
    report.text_length_before = text_length(reader)

    writer = PdfWriter()
    if reader.metadata:
        writer.add_metadata({k: str(v) for k, v in reader.metadata.items() if v is not None})

    for index, page in enumerate(reader.pages):
        page_report = PageReport(page_index=index, text_length=0, xobjects=count_page_xobjects(page))
        text_boxes = collect_text_boxes(page)
        page_report.text_boxes = len(text_boxes)
        page_report.obstruction_candidates = detect_image_obstructions(page, reader, text_boxes)
        page_report.obstruction_candidates.extend(detect_transparent_text_obstructions(page, reader))
        page_report.obstruction_candidates.extend(detect_transparent_text_form_obstructions(page, reader, text_boxes))
        _clean_page_annotations(page, page_report)
        if remove_detected_obstructions and any(
            candidate.kind == "transparent_text" for candidate in page_report.obstruction_candidates
        ):
            report.transparent_text_blocks_removed += _remove_transparent_text_blocks(page, reader)
            report.transparent_text_blocks_removed += _remove_transparent_text_form_invocations(
                page, reader, text_boxes
            )
        if remove_images:
            removed_images = _remove_image_xobjects(page, reader)
            report.image_xobjects_removed += removed_images
            page_report.xobjects = count_page_xobjects(page)
        elif remove_detected_obstructions and page_report.obstruction_candidates:
            names = {NameObject(candidate.name) for candidate in page_report.obstruction_candidates if candidate.kind == "image"}
            removed_images = _remove_image_xobjects(page, reader, names)
            report.image_xobjects_removed += removed_images
            page_report.xobjects = count_page_xobjects(page)
        if whiteout_regions:
            for rect in whiteout_regions:
                _add_whiteout(page, rect)
                report.whiteout_regions_applied += 1
        try:
            page_report.text_length = len(page.extract_text() or "")
        except Exception:
            page_report.text_length = 0
        report.signature_widgets_removed += page_report.signature_widgets_removed
        report.page_reports.append(page_report)
        writer.add_page(page)

    _clean_acroform(writer)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        writer.write(handle)

    after_reader = PdfReader(str(output_path), strict=False)
    report.text_length_after = text_length(after_reader)
    report.signature_fields_after = count_signature_fields(after_reader)
    report.signature_fields_removed = max(0, report.signature_fields_before - report.signature_fields_after)
    report.acroform_present_after = bool(resolve(after_reader.trailer.get("/Root", {})).get("/AcroForm"))
    summarize_obstructions(report)
    if report.image_xobjects_removed:
        report.warnings.append(
            f"Removed {report.image_xobjects_removed} image XObject(s); visual logos, stamps, or page images may be affected."
        )
    if report.text_length_after < report.text_length_before * 0.95:
        report.warnings.append("Text extraction length changed by more than 5%.")
    return report


def write_report(report: PdfReport, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove signature widgets and signature fields from text PDFs.")
    parser.add_argument("input", help="Input PDF path")
    parser.add_argument("output", help="Output PDF path")
    parser.add_argument("--report", help="JSON report path")
    parser.add_argument(
        "--whiteout",
        action="append",
        default=[],
        help="Optional rectangle x0,y0,x1,y1 to cover visually. Can be repeated.",
    )
    parser.add_argument(
        "--remove-images",
        action="store_true",
        help="Remove page image XObjects. Useful for image-based stamps or watermarks.",
    )
    parser.add_argument(
        "--keep-detected-obstructions",
        action="store_true",
        help="Do not remove detected image obstructions unless --remove-images is used.",
    )
    args = parser.parse_args()

    regions: list[list[float]] = []
    for value in args.whiteout:
        parts = [float(part.strip()) for part in value.split(",")]
        if len(parts) != 4:
            raise SystemExit("--whiteout expects x0,y0,x1,y1")
        regions.append(parts)

    report = clean_pdf(
        args.input,
        args.output,
        remove_detected_obstructions=not args.keep_detected_obstructions,
        remove_images=args.remove_images,
        whiteout_regions=regions or None,
    )
    if args.report:
        write_report(report, args.report)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
