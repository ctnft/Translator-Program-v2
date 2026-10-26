from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterator

from .models import IntegrityResult, PresentationStats, ReplacementResult, TextElement

# Microsoft Office MsoShapeType.msoGroup
# https://learn.microsoft.com/office/vba/api/office.msoshapetype
MSO_GROUP = 6
MSO_TRUE = -1
MSO_FALSE = 0


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


def _safe_set(obj: Any, name: str, value: Any) -> bool:
    if obj is None or value is None:
        return False
    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def _is_true(value: Any) -> bool:
    return value not in (None, 0, False)


def _safe_float(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _shape_text_style(shape: Any) -> tuple[float | None, bool | None, bool | None]:
    try:
        text_range = shape.TextFrame.TextRange
        font = text_range.Font
        size = _safe_float(_safe_get(font, "Size"))
        bold_raw = _safe_get(font, "Bold")
        italic_raw = _safe_get(font, "Italic")
        bold = None if bold_raw is None else _is_true(bold_raw)
        italic = None if italic_raw is None else _is_true(italic_raw)
        return size, bold, italic
    except Exception:
        return None, None, None


def _element_geometry(shape: Any) -> dict[str, float | None]:
    return {
        "left": _safe_float(_safe_get(shape, "Left")),
        "top": _safe_float(_safe_get(shape, "Top")),
        "width": _safe_float(_safe_get(shape, "Width")),
        "height": _safe_float(_safe_get(shape, "Height")),
    }


def _iter_com_collection(collection: Any) -> Iterator[tuple[int, Any]]:
    count = int(_safe_get(collection, "Count", 0) or 0)
    for index in range(1, count + 1):
        try:
            yield index, collection.Item(index)
        except Exception:
            # Some dynamic COM collections expose default __call__ access.
            yield index, collection(index)


class PowerPointWalker:
    """Read and minimally mutate an already-open PowerPoint presentation.

    The walker is deliberately independent from pywin32 imports so its traversal
    logic can be unit-tested with fake COM objects on non-Windows systems.
    """

    def inspect(self, presentation: Any) -> tuple[PresentationStats, list[TextElement]]:
        page_setup = _safe_get(presentation, "PageSetup")
        stats = PresentationStats(
            presentation_name=str(_safe_get(presentation, "Name", "")),
            slide_count=int(_safe_get(_safe_get(presentation, "Slides"), "Count", 0) or 0),
            slide_width=_safe_float(_safe_get(page_setup, "SlideWidth")),
            slide_height=_safe_float(_safe_get(page_setup, "SlideHeight")),
        )
        elements: list[TextElement] = []

        slides = _safe_get(presentation, "Slides")
        for slide_index, slide in _iter_com_collection(slides):
            shapes = _safe_get(slide, "Shapes")
            for shape_index, shape in _iter_com_collection(shapes):
                self._inspect_shape(
                    shape=shape,
                    slide_index=slide_index,
                    shape_path=(shape_index,),
                    group_path=(),
                    stats=stats,
                    elements=elements,
                )

        stats.text_element_count = len(elements)
        return stats, elements

    def _inspect_shape(
        self,
        shape: Any,
        slide_index: int,
        shape_path: tuple[int, ...],
        group_path: tuple[int, ...],
        stats: PresentationStats,
        elements: list[TextElement],
    ) -> None:
        stats.shape_count += 1
        shape_type = int(_safe_get(shape, "Type", 0) or 0)
        shape_id = _safe_get(shape, "Id")
        shape_name = str(_safe_get(shape, "Name", f"shape_{shape_path[-1]}"))

        if shape_type == MSO_GROUP:
            stats.group_count += 1
            group_items = _safe_get(shape, "GroupItems")
            for child_index, child in _iter_com_collection(group_items):
                self._inspect_shape(
                    shape=child,
                    slide_index=slide_index,
                    shape_path=shape_path + (child_index,),
                    group_path=group_path + (child_index,),
                    stats=stats,
                    elements=elements,
                )
            return

        if _is_true(_safe_get(shape, "HasTable", 0)):
            stats.table_count += 1
            table = _safe_get(shape, "Table")
            rows = int(_safe_get(_safe_get(table, "Rows"), "Count", 0) or 0)
            cols = int(_safe_get(_safe_get(table, "Columns"), "Count", 0) or 0)
            # PowerPoint merged cells can be addressable through multiple row/column
            # coordinates while pointing at the same visible cell. Translate/write
            # that physical cell once, otherwise the first write makes later aliases
            # fail with "source segment tidak ditemukan".
            seen_visible_cells: set[tuple[Any, ...]] = set()
            for row in range(1, rows + 1):
                for col in range(1, cols + 1):
                    stats.table_cell_count += 1
                    try:
                        cell_shape = table.Cell(row, col).Shape
                        text = self._read_shape_text(cell_shape)
                    except Exception as exc:
                        stats.warnings.append(
                            f"Slide {slide_index} table {shape_name} cell {row},{col}: {exc}"
                        )
                        continue
                    if text.strip():
                        cell_geometry = _element_geometry(cell_shape)
                        geom_values = (
                            cell_geometry["left"],
                            cell_geometry["top"],
                            cell_geometry["width"],
                            cell_geometry["height"],
                        )
                        cell_id = _safe_get(cell_shape, "Id")
                        if any(value is not None for value in geom_values):
                            visible_key = (*geom_values, text)
                        else:
                            visible_key = ("cell_id", cell_id, text)
                        if visible_key in seen_visible_cells:
                            continue
                        seen_visible_cells.add(visible_key)

                        font_size, bold, italic = _shape_text_style(cell_shape)
                        elements.append(
                            TextElement(
                                slide_index=slide_index,
                                shape_id=shape_id,
                                shape_name=shape_name,
                                kind="table_cell",
                                text=text,
                                shape_path=shape_path,
                                group_path=group_path,
                                row=row,
                                column=col,
                                font_size=font_size,
                                bold=bold,
                                italic=italic,
                                placeholder_type=(
                                    int(_safe_get(_safe_get(shape, "PlaceholderFormat"), "Type"))
                                    if _safe_get(_safe_get(shape, "PlaceholderFormat"), "Type") is not None
                                    else None
                                ),
                                **_element_geometry(shape),
                            )
                        )
            return

        if _is_true(_safe_get(shape, "HasTextFrame", 0)):
            text = self._read_shape_text(shape)
            if text.strip():
                stats.text_shape_count += 1
                if group_path:
                    stats.grouped_text_shape_count += 1
                font_size, bold, italic = _shape_text_style(shape)
                elements.append(
                    TextElement(
                        slide_index=slide_index,
                        shape_id=shape_id,
                        shape_name=shape_name,
                        kind="group_text" if group_path else "text_shape",
                        text=text,
                        shape_path=shape_path,
                        group_path=group_path,
                        font_size=font_size,
                        bold=bold,
                        italic=italic,
                        placeholder_type=(
                            int(_safe_get(_safe_get(shape, "PlaceholderFormat"), "Type"))
                            if _safe_get(_safe_get(shape, "PlaceholderFormat"), "Type") is not None
                            else None
                        ),
                        **_element_geometry(shape),
                    )
                )

    def _read_shape_text(self, shape: Any) -> str:
        if not _is_true(_safe_get(shape, "HasTextFrame", 0)):
            return ""
        text_frame = _safe_get(shape, "TextFrame")
        text_range = _safe_get(text_frame, "TextRange")
        return str(_safe_get(text_range, "Text", "") or "")

    def replace_first(
        self,
        presentation: Any,
        find_text: str,
        replace_text: str,
        *,
        match_case: bool = False,
        whole_words: bool = False,
    ) -> ReplacementResult:
        slides = _safe_get(presentation, "Slides")
        for slide_index, slide in _iter_com_collection(slides):
            shapes = _safe_get(slide, "Shapes")
            for shape_index, shape in _iter_com_collection(shapes):
                result = self._replace_in_shape(
                    shape=shape,
                    slide_index=slide_index,
                    shape_path=(shape_index,),
                    group_path=(),
                    find_text=find_text,
                    replace_text=replace_text,
                    match_case=match_case,
                    whole_words=whole_words,
                )
                if result.replaced:
                    return result

        return ReplacementResult(False, find_text, replace_text)

    def _replace_in_shape(
        self,
        shape: Any,
        slide_index: int,
        shape_path: tuple[int, ...],
        group_path: tuple[int, ...],
        find_text: str,
        replace_text: str,
        match_case: bool,
        whole_words: bool,
    ) -> ReplacementResult:
        shape_type = int(_safe_get(shape, "Type", 0) or 0)
        shape_id = _safe_get(shape, "Id")
        shape_name = str(_safe_get(shape, "Name", f"shape_{shape_path[-1]}"))

        if shape_type == MSO_GROUP:
            group_items = _safe_get(shape, "GroupItems")
            for child_index, child in _iter_com_collection(group_items):
                result = self._replace_in_shape(
                    shape=child,
                    slide_index=slide_index,
                    shape_path=shape_path + (child_index,),
                    group_path=group_path + (child_index,),
                    find_text=find_text,
                    replace_text=replace_text,
                    match_case=match_case,
                    whole_words=whole_words,
                )
                if result.replaced:
                    return result
            return ReplacementResult(False, find_text, replace_text)

        if _is_true(_safe_get(shape, "HasTable", 0)):
            table = _safe_get(shape, "Table")
            rows = int(_safe_get(_safe_get(table, "Rows"), "Count", 0) or 0)
            cols = int(_safe_get(_safe_get(table, "Columns"), "Count", 0) or 0)
            for row in range(1, rows + 1):
                for col in range(1, cols + 1):
                    try:
                        cell_shape = table.Cell(row, col).Shape
                        text_range = cell_shape.TextFrame.TextRange
                        found = text_range.Replace(
                            find_text,
                            replace_text,
                            0,
                            MSO_TRUE if match_case else MSO_FALSE,
                            MSO_TRUE if whole_words else MSO_FALSE,
                        )
                    except Exception:
                        continue
                    if found is not None:
                        return ReplacementResult(
                            True,
                            find_text,
                            replace_text,
                            TextElement(
                                slide_index=slide_index,
                                shape_id=shape_id,
                                shape_name=shape_name,
                                kind="table_cell",
                                text=str(_safe_get(text_range, "Text", "")),
                                shape_path=shape_path,
                                group_path=group_path,
                                row=row,
                                column=col,
                            ),
                        )
            return ReplacementResult(False, find_text, replace_text)

        if _is_true(_safe_get(shape, "HasTextFrame", 0)):
            try:
                text_range = shape.TextFrame.TextRange
                found = text_range.Replace(
                    find_text,
                    replace_text,
                    0,
                    MSO_TRUE if match_case else MSO_FALSE,
                    MSO_TRUE if whole_words else MSO_FALSE,
                )
            except Exception:
                return ReplacementResult(False, find_text, replace_text)

            if found is not None:
                return ReplacementResult(
                    True,
                    find_text,
                    replace_text,
                    TextElement(
                        slide_index=slide_index,
                        shape_id=shape_id,
                        shape_name=shape_name,
                        kind="group_text" if group_path else "text_shape",
                        text=str(_safe_get(text_range, "Text", "")),
                        shape_path=shape_path,
                        group_path=group_path,
                    ),
                )

        return ReplacementResult(False, find_text, replace_text)

    def _resolve_shape(self, presentation: Any, element: TextElement) -> Any:
        slide = _safe_get(presentation, "Slides").Item(element.slide_index)
        if not element.shape_path:
            raise ValueError("TextElement tidak memiliki shape_path.")
        shape = _safe_get(slide, "Shapes").Item(element.shape_path[0])
        for child_index in element.shape_path[1:]:
            shape = _safe_get(shape, "GroupItems").Item(child_index)
        return shape

    def read_element_text(self, presentation: Any, element: TextElement) -> str:
        shape = self._resolve_shape(presentation, element)
        if element.kind == "table_cell":
            if element.row is None or element.column is None:
                raise ValueError("Table element tidak memiliki row/column.")
            shape = shape.Table.Cell(element.row, element.column).Shape
        return self._read_shape_text(shape)

    @staticmethod
    def _font_signature(font: Any) -> dict[str, Any]:
        if font is None:
            return {}
        style: dict[str, Any] = {}
        for name in ("Name", "Size", "Bold", "Italic", "Underline", "Shadow", "Emboss", "BaselineOffset"):
            value = _safe_get(font, name)
            if value is not None:
                style[name] = value
        color = _safe_get(font, "Color")
        rgb = _safe_get(color, "RGB")
        if rgb is not None:
            style["ColorRGB"] = rgb
        return style

    @staticmethod
    def _apply_font_signature(font: Any, style: dict[str, Any]) -> None:
        if font is None:
            return
        for name, value in style.items():
            if name == "ColorRGB":
                color = _safe_get(font, "Color")
                _safe_set(color, "RGB", value)
            else:
                _safe_set(font, name, value)

    @staticmethod
    def _split_offsets(text: str) -> list[tuple[int, int]]:
        """Return non-break text spans as zero-based [start,end) offsets."""
        spans: list[tuple[int, int]] = []
        start = 0
        for index, ch in enumerate(text):
            if ch in {"\r", "\v", "\n"}:
                spans.append((start, index))
                start = index + 1
        spans.append((start, len(text)))
        return spans

    @staticmethod
    def _paragraph_offsets(text: str) -> list[tuple[int, int]]:
        """Return PowerPoint paragraph spans using hard paragraph marks only.

        A vertical tab (\v / Shift+Enter) is a soft line break inside the same
        paragraph. Treating it as a paragraph boundary can accidentally copy
        paragraph-level properties such as bullets onto lines that never had
        them in the source.
        """
        spans: list[tuple[int, int]] = []
        start = 0
        for index, ch in enumerate(text):
            if ch == "\r":
                spans.append((start, index))
                start = index + 1
        spans.append((start, len(text)))
        return spans

    @staticmethod
    def _paragraph_signature(paragraph_format: Any) -> dict[str, Any]:
        if paragraph_format is None:
            return {}
        data: dict[str, Any] = {}
        for name in (
            "Alignment", "BaseLineAlignment", "SpaceBefore", "SpaceAfter", "SpaceWithin",
        ):
            value = _safe_get(paragraph_format, name)
            if value is not None:
                data[name] = value

        # Bullet is paragraph-level state.  PowerPoint may turn Bullet.Visible
        # back on merely by assigning Bullet.Type or Bullet.Character.  Therefore
        # a source paragraph with no bullet must capture ONLY Visible=False and
        # must never replay the remaining bullet properties.
        bullet = _safe_get(paragraph_format, "Bullet")
        if bullet is not None:
            visible_raw = _safe_get(bullet, "Visible")
            visible = _is_true(visible_raw)
            bullet_data: dict[str, Any] = {"Visible": visible}
            if visible:
                for name in ("Type", "Character", "RelativeSize", "UseTextColor", "UseTextFont"):
                    value = _safe_get(bullet, name)
                    if value is not None:
                        bullet_data[name] = value
            data["Bullet"] = bullet_data
        return data

    @staticmethod
    def _apply_paragraph_signature(paragraph_format: Any, data: dict[str, Any]) -> None:
        if paragraph_format is None:
            return

        # Restore non-bullet paragraph properties first.  Bullet state is handled
        # separately because Type/Character setters can have Visible side effects.
        for name, value in data.items():
            if name != "Bullet":
                _safe_set(paragraph_format, name, value)

        bullet_data = data.get("Bullet")
        if not isinstance(bullet_data, dict):
            return
        bullet = _safe_get(paragraph_format, "Bullet")
        if bullet is None:
            return

        visible = bool(bullet_data.get("Visible", False))
        if not visible:
            # Critical invariant: never touch Type/Character for a non-bulleted
            # source paragraph.  Writing either can create a new bullet in PPT.
            _safe_set(bullet, "Visible", 0)
            return

        # For a genuinely bulleted source paragraph, restore its details first
        # and make it visible only at the end.
        _safe_set(bullet, "Visible", 0)
        for bullet_name in ("Type", "Character", "RelativeSize", "UseTextColor", "UseTextFont"):
            if bullet_name in bullet_data:
                _safe_set(bullet, bullet_name, bullet_data[bullet_name])
        _safe_set(bullet, "Visible", -1)

    def _capture_paragraph_styles(self, text_range: Any, text: str) -> list[dict[str, Any]]:
        characters = _safe_get(text_range, "Characters")
        captured: list[dict[str, Any]] = []
        for start, end in self._paragraph_offsets(text):
            try:
                length = max(1, end - start)
                rng = characters(start + 1, length) if callable(characters) else None
                captured.append(self._paragraph_signature(_safe_get(rng, "ParagraphFormat")))
            except Exception:
                captured.append({})
        return captured

    def _restore_paragraph_styles(self, text_range: Any, target_text: str, styles: list[dict[str, Any]]) -> None:
        characters = _safe_get(text_range, "Characters")
        if not callable(characters):
            return
        for index, (start, end) in enumerate(self._paragraph_offsets(target_text)):
            if index >= len(styles) or not styles[index]:
                continue
            try:
                length = max(1, end - start)
                rng = characters(start + 1, length)
                self._apply_paragraph_signature(_safe_get(rng, "ParagraphFormat"), styles[index])
            except Exception:
                pass

    def _capture_segment_styles(self, text_range: Any, text: str) -> list[list[dict[str, Any]]]:
        """Capture character font style for each semantic line/paragraph.

        PowerPoint's Replace may extend the first character's format over newly
        inserted text. Capturing styles per character lets us reconstruct the same
        style pattern after a length-changing translation. Failures are best-effort:
        geometry preservation still applies even on unusual COM text objects.
        """
        captured: list[list[dict[str, Any]]] = []
        characters = _safe_get(text_range, "Characters")
        for start, end in self._split_offsets(text):
            styles: list[dict[str, Any]] = []
            for offset in range(start, end):
                try:
                    char_range = characters(offset + 1, 1) if callable(characters) else None
                    styles.append(self._font_signature(_safe_get(char_range, "Font")))
                except Exception:
                    styles.append({})
            captured.append(styles)
        return captured

    def _restore_segment_styles(
        self,
        text_range: Any,
        source_styles: list[list[dict[str, Any]]],
        target_text: str,
    ) -> None:
        characters = _safe_get(text_range, "Characters")
        if not callable(characters):
            return
        target_spans = self._split_offsets(target_text)
        for segment_index, (start, end) in enumerate(target_spans):
            target_len = max(0, end - start)
            if target_len == 0 or segment_index >= len(source_styles):
                continue
            styles = source_styles[segment_index]
            if not styles:
                continue
            source_len = len(styles)
            mapped: list[dict[str, Any]] = []
            for j in range(target_len):
                source_index = min(source_len - 1, int(j * source_len / target_len))
                mapped.append(styles[source_index])

            run_start = 0
            while run_start < target_len:
                style = mapped[run_start]
                run_end = run_start + 1
                while run_end < target_len and mapped[run_end] == style:
                    run_end += 1
                if style:
                    try:
                        rng = characters(start + run_start + 1, run_end - run_start)
                        self._apply_font_signature(_safe_get(rng, "Font"), style)
                    except Exception:
                        pass
                run_start = run_end

    @staticmethod
    def _capture_geometry(shape: Any) -> dict[str, Any]:
        return {
            "Left": _safe_get(shape, "Left"),
            "Top": _safe_get(shape, "Top"),
            "Width": _safe_get(shape, "Width"),
            "Height": _safe_get(shape, "Height"),
            "Rotation": _safe_get(shape, "Rotation"),
        }

    @staticmethod
    def _restore_geometry(shape: Any, state: dict[str, Any]) -> None:
        for name in ("Left", "Top", "Width", "Height", "Rotation"):
            _safe_set(shape, name, state.get(name))

    @staticmethod
    def _capture_textframe_state(shape: Any) -> dict[str, Any]:
        frame = _safe_get(shape, "TextFrame")
        frame2 = _safe_get(shape, "TextFrame2")
        return {
            "frame": frame,
            "frame2": frame2,
            "AutoSize": _safe_get(frame, "AutoSize"),
            "AutoSize2": _safe_get(frame2, "AutoSize"),
            "WordWrap": _safe_get(frame, "WordWrap"),
            "WordWrap2": _safe_get(frame2, "WordWrap"),
            "MarginLeft": _safe_get(frame, "MarginLeft"),
            "MarginRight": _safe_get(frame, "MarginRight"),
            "MarginTop": _safe_get(frame, "MarginTop"),
            "MarginBottom": _safe_get(frame, "MarginBottom"),
            "VerticalAnchor": _safe_get(frame, "VerticalAnchor"),
        }

    @staticmethod
    def _freeze_and_restore_textframe(state: dict[str, Any], *, final: bool) -> None:
        frame = state.get("frame")
        frame2 = state.get("frame2")
        # During and after translation keep AutoSize disabled. Re-enabling an
        # original ShapeToFitText mode would silently change Width/Height, which
        # violates source-faithful layout preservation.
        _safe_set(frame, "AutoSize", 0)
        _safe_set(frame2, "AutoSize", 0)
        if final:
            for name in ("WordWrap", "MarginLeft", "MarginRight", "MarginTop", "MarginBottom", "VerticalAnchor"):
                _safe_set(frame, name, state.get(name))
            _safe_set(frame2, "WordWrap", state.get("WordWrap2"))

    @staticmethod
    def _capture_table_layout(table: Any) -> dict[str, list[Any]]:
        rows = _safe_get(table, "Rows")
        cols = _safe_get(table, "Columns")
        row_heights: list[Any] = []
        col_widths: list[Any] = []
        try:
            row_count = int(_safe_get(rows, "Count", 0) or 0)
            for index in range(1, row_count + 1):
                row_heights.append(_safe_get(rows.Item(index), "Height"))
        except Exception:
            row_heights = []
        try:
            col_count = int(_safe_get(cols, "Count", 0) or 0)
            for index in range(1, col_count + 1):
                col_widths.append(_safe_get(cols.Item(index), "Width"))
        except Exception:
            col_widths = []
        return {"row_heights": row_heights, "col_widths": col_widths}

    @staticmethod
    def _restore_table_layout(table: Any, state: dict[str, list[Any]]) -> None:
        rows = _safe_get(table, "Rows")
        cols = _safe_get(table, "Columns")
        for index, value in enumerate(state.get("row_heights", []), start=1):
            try:
                _safe_set(rows.Item(index), "Height", value)
            except Exception:
                pass
        for index, value in enumerate(state.get("col_widths", []), start=1):
            try:
                _safe_set(cols.Item(index), "Width", value)
            except Exception:
                pass

    def _resolve_shape_chain(self, presentation: Any, element: TextElement) -> list[Any]:
        slide = _safe_get(presentation, "Slides").Item(element.slide_index)
        if not element.shape_path:
            raise ValueError("TextElement tidak memiliki shape_path.")
        chain: list[Any] = []
        shape = _safe_get(slide, "Shapes").Item(element.shape_path[0])
        chain.append(shape)
        for child_index in element.shape_path[1:]:
            shape = _safe_get(shape, "GroupItems").Item(child_index)
            chain.append(shape)
        return chain

    def apply_segment_replacements(
        self,
        presentation: Any,
        element: TextElement,
        replacements: list[tuple[str, str]],
    ) -> str:
        chain = self._resolve_shape_chain(presentation, element)
        shape = chain[-1]
        geometry_states = [(item, self._capture_geometry(item)) for item in chain]
        table_layout: tuple[Any, dict[str, list[Any]]] | None = None
        if element.kind == "table_cell":
            if element.row is None or element.column is None:
                raise ValueError("Table element tidak memiliki row/column.")
            table = shape.Table
            table_layout = (table, self._capture_table_layout(table))
            shape = table.Cell(element.row, element.column).Shape
            geometry_states.append((shape, self._capture_geometry(shape)))

        frame_state = self._capture_textframe_state(shape)
        text_range = shape.TextFrame.TextRange
        source_text = str(_safe_get(text_range, "Text", ""))
        source_styles = self._capture_segment_styles(text_range, source_text)
        paragraph_styles = self._capture_paragraph_styles(text_range, source_text)
        self._freeze_and_restore_textframe(frame_state, final=False)

        try:
            for source, target in replacements:
                if source == target or not source:
                    continue
                found = text_range.Replace(source, target, 0, MSO_TRUE, MSO_FALSE)
                if found is None:
                    raise ValueError(
                        f"Source segment tidak ditemukan pada target element: {source!r}"
                    )
            final_text = str(_safe_get(text_range, "Text", ""))
            self._restore_segment_styles(text_range, source_styles, final_text)
            self._restore_paragraph_styles(text_range, final_text, paragraph_styles)
        finally:
            self._freeze_and_restore_textframe(frame_state, final=True)
            if table_layout is not None:
                self._restore_table_layout(table_layout[0], table_layout[1])
            # Restore deepest object first, then its group/container ancestors.
            for item, state in reversed(geometry_states):
                self._restore_geometry(item, state)

        return str(_safe_get(text_range, "Text", ""))

    @staticmethod
    def element_key(element: TextElement) -> str:
        path = ".".join(str(i) for i in element.shape_path)
        cell = f":r{element.row}c{element.column}" if element.kind == "table_cell" else ""
        return f"slide{element.slide_index}:shape{path}:{element.kind}{cell}"

    def structure_snapshot(self, presentation: Any) -> list[dict[str, Any]]:
        snapshot: list[dict[str, Any]] = []
        slides = _safe_get(presentation, "Slides")
        for slide_index, slide in _iter_com_collection(slides):
            shapes = _safe_get(slide, "Shapes")
            for shape_index, shape in _iter_com_collection(shapes):
                self._snapshot_shape(
                    shape,
                    slide_index,
                    (shape_index,),
                    snapshot,
                )
        return snapshot

    def _snapshot_shape(
        self,
        shape: Any,
        slide_index: int,
        path: tuple[int, ...],
        snapshot: list[dict[str, Any]],
    ) -> None:
        record = {
            "slide": slide_index,
            "path": path,
            "type": int(_safe_get(shape, "Type", 0) or 0),
            "name": str(_safe_get(shape, "Name", "")),
            "left": self._round_number(_safe_get(shape, "Left")),
            "top": self._round_number(_safe_get(shape, "Top")),
            "width": self._round_number(_safe_get(shape, "Width")),
            "height": self._round_number(_safe_get(shape, "Height")),
            "rotation": self._round_number(_safe_get(shape, "Rotation")),
        }
        if _is_true(_safe_get(shape, "HasTable", 0)):
            table = _safe_get(shape, "Table")
            record["table_rows"] = int(
                _safe_get(_safe_get(table, "Rows"), "Count", 0) or 0
            )
            record["table_columns"] = int(
                _safe_get(_safe_get(table, "Columns"), "Count", 0) or 0
            )
        snapshot.append(record)

        if record["type"] == MSO_GROUP:
            for child_index, child in _iter_com_collection(_safe_get(shape, "GroupItems")):
                self._snapshot_shape(
                    child,
                    slide_index,
                    path + (child_index,),
                    snapshot,
                )

    @staticmethod
    def _round_number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return round(float(value), 4)
        except (TypeError, ValueError):
            return None

    def compare_structure(
        self,
        before: list[dict[str, Any]],
        after: list[dict[str, Any]],
    ) -> IntegrityResult:
        differences: list[str] = []

        if len(before) != len(after):
            differences.append(
                f"Shape snapshot count changed: {len(before)} -> {len(after)}"
            )

        before_map = {(item["slide"], tuple(item["path"])): item for item in before}
        after_map = {(item["slide"], tuple(item["path"])): item for item in after}

        all_keys = sorted(set(before_map) | set(after_map))
        checked_fields = (
            "type",
            "left",
            "top",
            "width",
            "height",
            "rotation",
            "table_rows",
            "table_columns",
        )

        for key in all_keys:
            left = before_map.get(key)
            right = after_map.get(key)
            if left is None:
                differences.append(f"Shape added at {key}")
                continue
            if right is None:
                differences.append(f"Shape missing at {key}")
                continue
            for field in checked_fields:
                if left.get(field) != right.get(field):
                    differences.append(
                        f"{key} field {field}: {left.get(field)!r} -> {right.get(field)!r}"
                    )

        return IntegrityResult(passed=not differences, differences=differences)
