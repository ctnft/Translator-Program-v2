from __future__ import annotations

from collections import Counter
from typing import Any, Iterator

from .models import WordDocumentStats, WordElement, WordIntegrityResult

# Word constants (late-binding friendly; no win32com import needed for tests)
WD_WITHIN_TABLE = 12
WD_ACTIVE_END_ADJUSTED_PAGE_NUMBER = 1
WD_HEADER_FOOTER_PRIMARY = 1
WD_HEADER_FOOTER_FIRST_PAGE = 2
WD_HEADER_FOOTER_EVEN_PAGES = 3


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe_set(obj: Any, name: str, value: Any) -> bool:
    if obj is None:
        return False
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def _iter_collection(collection: Any) -> Iterator[tuple[int, Any]]:
    count = int(_safe_get(collection, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            yield index, collection.Item(index)
        except Exception:
            yield index, collection(index)


def _trim_terminal_markers(text: str) -> tuple[str, int]:
    """Strip Word container terminators but preserve meaningful internal breaks.

    Paragraphs end with CR; table cells end with CR + cell marker (\x07).
    Returns (content, number_of_terminal_characters_removed).
    """
    if text.endswith("\r\x07"):
        return text[:-2], 2
    if text.endswith("\x07"):
        text = text[:-1]
        removed = 1
        if text.endswith("\r"):
            return text[:-1], 2
        return text, removed
    if text.endswith("\r"):
        return text[:-1], 1
    return text, 0


def _range_text(range_obj: Any) -> tuple[str, int]:
    return _trim_terminal_markers(str(_safe_get(range_obj, "Text", "") or ""))


def _range_information(range_obj: Any, code: int, default: Any = None) -> Any:
    try:
        info = _safe_get(range_obj, "Information")
        if callable(info):
            return info(code)
        return info[code]
    except Exception:
        return default


def _style_name(range_obj: Any) -> str:
    style = _safe_get(range_obj, "Style")
    if style is None:
        return ""
    name = _safe_get(style, "NameLocal")
    return str(name if name is not None else style or "")


def _outline_level(range_obj: Any) -> int | None:
    value = _safe_get(_safe_get(range_obj, "ParagraphFormat"), "OutlineLevel")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _count(collection: Any) -> int:
    try:
        return int(_safe_get(collection, "Count", 0) or 0)
    except Exception:
        return 0


def _font_signature(font: Any) -> tuple[Any, ...]:
    if font is None:
        return ()
    color = _safe_get(_safe_get(font, "Color"), "RGB")
    return tuple(
        _safe_get(font, name)
        for name in ("Name", "NameAscii", "NameFarEast", "Size", "Bold", "Italic", "Underline", "StrikeThrough")
    ) + (color,)


def _apply_font_signature(font: Any, signature: tuple[Any, ...]) -> None:
    if not signature or font is None:
        return
    names = ("Name", "NameAscii", "NameFarEast", "Size", "Bold", "Italic", "Underline", "StrikeThrough")
    for name, value in zip(names, signature[: len(names)]):
        if value is not None:
            _safe_set(font, name, value)
    if len(signature) > len(names) and signature[-1] is not None:
        _safe_set(_safe_get(font, "Color"), "RGB", signature[-1])


def _paragraph_signature(paragraph_format: Any) -> dict[str, Any]:
    names = (
        "Alignment", "LeftIndent", "RightIndent", "FirstLineIndent", "SpaceBefore", "SpaceAfter",
        "LineSpacing", "LineSpacingRule", "KeepTogether", "KeepWithNext", "PageBreakBefore", "WidowControl",
    )
    return {name: _safe_get(paragraph_format, name) for name in names if _safe_get(paragraph_format, name) is not None}


def _apply_paragraph_signature(paragraph_format: Any, signature: dict[str, Any]) -> None:
    for name, value in signature.items():
        _safe_set(paragraph_format, name, value)


class WordWalker:
    """Read/write Word content with a strict text-only mutation contract.

    Supported Phase 5.2.x surfaces:
    - normal body paragraphs (outside tables)
    - table cells
    - section headers and footers
    - Word text boxes/shapes with TextFrame text

    Fields/content controls are deliberately preserved rather than rewritten in this
    first adapter because replacing their range can destroy Word semantics.
    """

    @staticmethod
    def element_key(element: WordElement) -> str:
        if element.kind == "table_cell":
            return f"word:{element.story}:table{element.table_index}:cell{element.cell_index}:r{element.row}:c{element.column}"
        if element.kind in {"header", "footer"}:
            return (
                f"word:{element.kind}:section{element.section_index}:type{element.header_footer_type}:"
                f"p{element.paragraph_index}:range{element.range_start}-{element.range_end}"
            )
        if element.kind == "textbox":
            return (
                f"word:{element.story}:section{element.section_index or 0}:shape{element.shape_index}:"
                f"range{element.range_start}-{element.range_end}"
            )
        return f"word:main:p{element.paragraph_index}:range{element.range_start}-{element.range_end}"

    def inspect(self, document: Any) -> tuple[WordDocumentStats, list[WordElement]]:
        stats = WordDocumentStats(
            document_name=str(_safe_get(document, "Name", "")),
            section_count=_count(_safe_get(document, "Sections")),
            table_count=_count(_safe_get(document, "Tables")),
        )
        try:
            stats.page_count = int(document.ComputeStatistics(2))  # wdStatisticPages
        except Exception:
            stats.page_count = None

        elements: list[WordElement] = []
        heading_stack: list[str] = []

        # Main body paragraphs, excluding table paragraphs to avoid duplicate translation.
        for paragraph_index, paragraph in _iter_collection(_safe_get(document, "Paragraphs")):
            rng = _safe_get(paragraph, "Range")
            if rng is None:
                continue
            if bool(_range_information(rng, WD_WITHIN_TABLE, False)):
                continue
            text, removed = _range_text(rng)
            if not text.strip():
                continue
            stats.paragraph_count += 1
            level = _outline_level(rng)
            style = _style_name(rng)
            if level is not None and 1 <= level <= 9:
                heading_stack = heading_stack[: level - 1]
                heading_stack.append(text.strip())
            start = int(_safe_get(rng, "Start", 0) or 0)
            end = int(_safe_get(rng, "End", start + len(text)) or (start + len(text))) - removed
            elements.append(
                WordElement(
                    kind="paragraph",
                    text=text,
                    story="main",
                    range_start=start,
                    range_end=end,
                    page_number=self._page_number(rng),
                    paragraph_index=paragraph_index,
                    style_name=style,
                    outline_level=level,
                    heading_path=tuple(heading_stack),
                    has_fields=_count(_safe_get(rng, "Fields")) > 0,
                    has_content_controls=_count(_safe_get(rng, "ContentControls")) > 0,
                )
            )

        # Tables. Cells collection handles merged cells more safely than row/column loops.
        for table_index, table in _iter_collection(_safe_get(document, "Tables")):
            cells = _safe_get(_safe_get(table, "Range"), "Cells") or _safe_get(table, "Cells")
            seen_ranges: set[tuple[int, int]] = set()
            for cell_index, cell in _iter_collection(cells):
                rng = _safe_get(cell, "Range")
                if rng is None:
                    continue
                text, removed = _range_text(rng)
                start = int(_safe_get(rng, "Start", 0) or 0)
                end_raw = int(_safe_get(rng, "End", start + len(text)) or (start + len(text)))
                end = end_raw - removed
                range_key = (start, end)
                if range_key in seen_ranges:
                    continue
                seen_ranges.add(range_key)
                if not text.strip():
                    continue
                stats.table_cell_count += 1
                elements.append(
                    WordElement(
                        kind="table_cell",
                        text=text,
                        story="main",
                        range_start=start,
                        range_end=end,
                        page_number=self._page_number(rng),
                        table_index=table_index,
                        cell_index=cell_index,
                        row=self._int_or_none(_safe_get(cell, "RowIndex")),
                        column=self._int_or_none(_safe_get(cell, "ColumnIndex")),
                        style_name=_style_name(rng),
                        heading_path=self._heading_for_position(elements, start),
                        has_fields=_count(_safe_get(rng, "Fields")) > 0,
                        has_content_controls=_count(_safe_get(rng, "ContentControls")) > 0,
                    )
                )

        # Body textboxes/shapes.
        self._inspect_shapes(_safe_get(document, "Shapes"), elements, stats, story="main", section_index=None)

        # Headers and footers per section. Deduplicate linked-to-previous ranges.
        seen_hf: set[tuple[str, int, int, str]] = set()
        for section_index, section in _iter_collection(_safe_get(document, "Sections")):
            for kind, collection_name in (("header", "Headers"), ("footer", "Footers")):
                collection = _safe_get(section, collection_name)
                for hf_type in (WD_HEADER_FOOTER_PRIMARY, WD_HEADER_FOOTER_FIRST_PAGE, WD_HEADER_FOOTER_EVEN_PAGES):
                    try:
                        hf = collection.Item(hf_type)
                    except Exception:
                        continue
                    if not bool(_safe_get(hf, "Exists", True)):
                        continue
                    # Linked headers/footers share the previous section's underlying story.
                    # Inspect/write the source story once; editing the parent updates linked sections.
                    if section_index > 1 and bool(_safe_get(hf, "LinkedToPrevious", False)):
                        continue
                    hf_range = _safe_get(hf, "Range")
                    if hf_range is None:
                        continue
                    for paragraph_index, paragraph in _iter_collection(_safe_get(hf_range, "Paragraphs")):
                        rng = _safe_get(paragraph, "Range")
                        text, removed = _range_text(rng)
                        if not text.strip():
                            continue
                        start = int(_safe_get(rng, "Start", 0) or 0)
                        end = int(_safe_get(rng, "End", start + len(text)) or (start + len(text))) - removed
                        dedup = (f"{kind}:{section_index}:{hf_type}", start, end, text)
                        if dedup in seen_hf:
                            continue
                        seen_hf.add(dedup)
                        stats.header_footer_count += 1
                        elements.append(
                            WordElement(
                                kind=kind,
                                text=text,
                                story=f"{kind}_{hf_type}",
                                range_start=start,
                                range_end=end,
                                section_index=section_index,
                                paragraph_index=paragraph_index,
                                header_footer_type=hf_type,
                                style_name=_style_name(rng),
                                has_fields=_count(_safe_get(rng, "Fields")) > 0,
                                has_content_controls=_count(_safe_get(rng, "ContentControls")) > 0,
                            )
                        )
                    self._inspect_shapes(
                        _safe_get(hf, "Shapes"), elements, stats,
                        story=f"{kind}_{hf_type}", section_index=section_index,
                        header_footer_type=hf_type,
                    )

        stats.text_element_count = len(elements)
        return stats, elements

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _page_number(rng: Any) -> int | None:
        value = _range_information(rng, WD_ACTIVE_END_ADJUSTED_PAGE_NUMBER)
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _heading_for_position(elements: list[WordElement], position: int) -> tuple[str, ...]:
        headings: tuple[str, ...] = ()
        for element in elements:
            if element.kind != "paragraph" or element.range_start is None or element.range_start > position:
                continue
            if element.outline_level is not None and 1 <= element.outline_level <= 9:
                headings = element.heading_path
        return headings

    def _inspect_shapes(
        self,
        shapes: Any,
        elements: list[WordElement],
        stats: WordDocumentStats,
        *,
        story: str,
        section_index: int | None,
        header_footer_type: int | None = None,
    ) -> None:
        for shape_index, shape in _iter_collection(shapes):
            text_frame = _safe_get(shape, "TextFrame")
            if text_frame is None or not bool(_safe_get(text_frame, "HasText", False)):
                continue
            rng = _safe_get(text_frame, "TextRange")
            if rng is None:
                continue
            text, removed = _range_text(rng)
            if not text.strip():
                continue
            start = int(_safe_get(rng, "Start", 0) or 0)
            end = int(_safe_get(rng, "End", start + len(text)) or (start + len(text))) - removed
            stats.textbox_count += 1
            elements.append(
                WordElement(
                    kind="textbox",
                    text=text,
                    story=story,
                    range_start=start,
                    range_end=end,
                    section_index=section_index,
                    shape_index=shape_index,
                    shape_name=str(_safe_get(shape, "Name", f"shape_{shape_index}")),
                    header_footer_type=header_footer_type,
                    style_name=_style_name(rng),
                    has_fields=_count(_safe_get(rng, "Fields")) > 0,
                    has_content_controls=_count(_safe_get(rng, "ContentControls")) > 0,
                )
            )

    def _resolve_range(self, document: Any, element: WordElement) -> Any:
        if element.kind == "paragraph":
            rng = document.Paragraphs.Item(element.paragraph_index).Range.Duplicate
        elif element.kind == "table_cell":
            table = document.Tables.Item(element.table_index)
            cells = _safe_get(_safe_get(table, "Range"), "Cells") or table.Cells
            rng = cells.Item(element.cell_index).Range.Duplicate
        elif element.kind in {"header", "footer"}:
            section = document.Sections.Item(element.section_index)
            collection = section.Headers if element.kind == "header" else section.Footers
            hf = collection.Item(element.header_footer_type)
            rng = hf.Range.Paragraphs.Item(element.paragraph_index).Range.Duplicate
        elif element.kind == "textbox":
            if element.story == "main":
                shape = document.Shapes.Item(element.shape_index)
            else:
                kind = "header" if element.story.startswith("header_") else "footer"
                section = document.Sections.Item(element.section_index)
                collection = section.Headers if kind == "header" else section.Footers
                hf = collection.Item(element.header_footer_type)
                shape = hf.Shapes.Item(element.shape_index)
            rng = shape.TextFrame.TextRange.Duplicate
        else:
            raise ValueError(f"Word element kind tidak didukung: {element.kind}")

        # Restrict duplicate range to content only, preserving paragraph/cell marks.
        text, removed = _range_text(rng)
        if removed:
            try:
                rng.End = int(rng.End) - removed
            except Exception:
                pass
        return rng

    def read_element_text(self, document: Any, element: WordElement) -> str:
        rng = self._resolve_range(document, element)
        return str(_safe_get(rng, "Text", "") or "")

    @staticmethod
    def _font_runs(rng: Any) -> list[tuple[int, int, tuple[Any, ...]]]:
        text = str(_safe_get(rng, "Text", "") or "")
        if not text:
            return []
        chars = _safe_get(rng, "Characters")
        count = min(_count(chars), len(text))
        if count <= 0:
            return [(0, len(text), _font_signature(_safe_get(rng, "Font")))]
        runs: list[tuple[int, int, tuple[Any, ...]]] = []
        start = 0
        current = None
        for i in range(1, count + 1):
            try:
                sig = _font_signature(chars.Item(i).Font)
            except Exception:
                sig = _font_signature(_safe_get(rng, "Font"))
            if current is None:
                current = sig
            elif sig != current:
                runs.append((start, i - 1, current))
                start = i - 1
                current = sig
        runs.append((start, count, current or ()))
        if count < len(text):
            runs[-1] = (runs[-1][0], len(text), runs[-1][2])
        return runs

    @staticmethod
    def _apply_runs(rng: Any, source_len: int, target_len: int, runs: list[tuple[int, int, tuple[Any, ...]]]) -> None:
        if not runs or target_len <= 0:
            return
        base = int(_safe_get(rng, "Start", 0) or 0)
        total = max(1, source_len)
        previous_end = 0
        for index, (start, end, signature) in enumerate(runs):
            if index == len(runs) - 1:
                mapped_end = target_len
            else:
                mapped_end = max(previous_end, min(target_len, round(end / total * target_len)))
            mapped_start = previous_end
            if mapped_end <= mapped_start:
                continue
            part = rng.Duplicate
            part.SetRange(base + mapped_start, base + mapped_end)
            _apply_font_signature(_safe_get(part, "Font"), signature)
            previous_end = mapped_end

    def replace_text(self, document: Any, element: WordElement, target_text: str) -> dict[str, Any]:
        if element.has_fields:
            raise ValueError("Element mengandung Word field; Phase 5.2.x preserves field untuk mencegah field rusak.")
        if element.has_content_controls:
            raise ValueError("Element mengandung content control; Phase 5.2.x belum menulis ke content control.")

        rng = self._resolve_range(document, element)
        source_text = str(_safe_get(rng, "Text", "") or "")
        paragraph_sig = _paragraph_signature(_safe_get(rng, "ParagraphFormat"))
        font_runs = self._font_runs(rng)
        style_before = _style_name(rng)

        table_snapshot = None
        if element.kind == "table_cell":
            table = document.Tables.Item(element.table_index)
            table_snapshot = self._snapshot_table(table)
            _safe_set(table, "AllowAutoFit", False)

        # Because paragraph/cell terminators were excluded from rng, Word list/bullet
        # identity and paragraph boundaries are not replaced.
        rng.Text = target_text
        new_rng = self._resolve_range(document, element)
        # Range.End can be stale after changing text; resolve by start + target length.
        try:
            new_rng.End = int(new_rng.Start) + len(target_text)
        except Exception:
            pass
        _apply_paragraph_signature(_safe_get(new_rng, "ParagraphFormat"), paragraph_sig)
        self._apply_runs(new_rng, len(source_text), len(target_text), font_runs)

        if table_snapshot is not None:
            self._restore_table(document.Tables.Item(element.table_index), table_snapshot)

        actual = str(_safe_get(new_rng, "Text", "") or "")
        return {
            "text": actual,
            "style_before": style_before,
            "style_after": _style_name(new_rng),
            "font_style_sequence_before": [run[2] for run in font_runs],
            "font_style_sequence_after": [run[2] for run in self._font_runs(new_rng)],
        }

    @staticmethod
    def _snapshot_table(table: Any) -> dict[str, Any]:
        columns = []
        for _, col in _iter_collection(_safe_get(table, "Columns")):
            columns.append(_safe_get(col, "Width"))
        rows = []
        for _, row in _iter_collection(_safe_get(table, "Rows")):
            rows.append((_safe_get(row, "Height"), _safe_get(row, "HeightRule")))
        return {"allow_auto_fit": _safe_get(table, "AllowAutoFit"), "columns": columns, "rows": rows}

    @staticmethod
    def _restore_table(table: Any, snapshot: dict[str, Any]) -> None:
        for (index, col), width in zip(_iter_collection(_safe_get(table, "Columns")), snapshot.get("columns", [])):
            if width is not None:
                _safe_set(col, "Width", width)
        for (index, row), values in zip(_iter_collection(_safe_get(table, "Rows")), snapshot.get("rows", [])):
            height, rule = values
            if height is not None:
                _safe_set(row, "Height", height)
            if rule is not None:
                _safe_set(row, "HeightRule", rule)
        original = snapshot.get("allow_auto_fit")
        if original is not None:
            _safe_set(table, "AllowAutoFit", original)

    def structure_snapshot(self, document: Any) -> dict[str, Any]:
        stats, elements = self.inspect(document)
        kinds = Counter(e.kind for e in elements)
        tables = []
        for table_index, table in _iter_collection(_safe_get(document, "Tables")):
            tables.append({
                "table": table_index,
                "rows": _count(_safe_get(table, "Rows")),
                "columns": _count(_safe_get(table, "Columns")),
                "cells": _count(_safe_get(_safe_get(table, "Range"), "Cells") or _safe_get(table, "Cells")),
            })
        return {
            "sections": stats.section_count,
            "tables": tables,
            "kinds": dict(kinds),
            "textbox_count": stats.textbox_count,
        }

    @staticmethod
    def compare_structure(before: dict[str, Any], after: dict[str, Any]) -> WordIntegrityResult:
        differences: list[str] = []
        for key in ("sections", "tables", "kinds", "textbox_count"):
            if before.get(key) != after.get(key):
                differences.append(f"{key} changed: {before.get(key)!r} -> {after.get(key)!r}")
        return WordIntegrityResult(passed=not differences, differences=differences)
