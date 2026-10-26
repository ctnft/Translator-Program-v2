from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WordElement:
    kind: str
    text: str
    story: str = "main"
    range_start: int | None = None
    range_end: int | None = None
    page_number: int | None = None
    section_index: int | None = None
    paragraph_index: int | None = None
    table_index: int | None = None
    cell_index: int | None = None
    row: int | None = None
    column: int | None = None
    shape_index: int | None = None
    shape_name: str = ""
    header_footer_type: int | None = None
    style_name: str = ""
    outline_level: int | None = None
    heading_path: tuple[str, ...] = ()
    has_fields: bool = False
    has_content_controls: bool = False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["heading_path"] = list(self.heading_path)
        return data


@dataclass
class WordDocumentStats:
    document_name: str = ""
    page_count: int | None = None
    section_count: int = 0
    paragraph_count: int = 0
    table_count: int = 0
    table_cell_count: int = 0
    header_footer_count: int = 0
    textbox_count: int = 0
    text_element_count: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WordIntegrityResult:
    passed: bool
    differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
