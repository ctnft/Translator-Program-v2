from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TextElement:
    slide_index: int
    shape_id: int | None
    shape_name: str
    kind: str
    text: str
    shape_path: tuple[int, ...] = ()
    group_path: tuple[int, ...] = ()
    row: int | None = None
    column: int | None = None
    left: float | None = None
    top: float | None = None
    width: float | None = None
    height: float | None = None
    font_size: float | None = None
    bold: bool | None = None
    italic: bool | None = None
    placeholder_type: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["shape_path"] = list(self.shape_path)
        data["group_path"] = list(self.group_path)
        return data


@dataclass
class PresentationStats:
    presentation_name: str = ""
    slide_count: int = 0
    slide_width: float | None = None
    slide_height: float | None = None
    shape_count: int = 0
    group_count: int = 0
    text_shape_count: int = 0
    grouped_text_shape_count: int = 0
    table_count: int = 0
    table_cell_count: int = 0
    text_element_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReplacementResult:
    replaced: bool
    find_text: str
    replace_text: str
    element: TextElement | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.element is not None:
            data["element"] = self.element.to_dict()
        return data


@dataclass
class IntegrityResult:
    passed: bool
    differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
