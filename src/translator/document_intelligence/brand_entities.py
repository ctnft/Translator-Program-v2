from __future__ import annotations

import re
from collections import defaultdict

from translator.powerpoint_com.models import TextElement

_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9'&.+/-]*")
_BRANDS_CUE = re.compile(r"\bbrands?\s*\|", re.I)
_BRAND_HEADER = re.compile(r"\b(?:product\s*/?\s*brand\s*name|brand\s*name|merek)\b", re.I)
_ONLY_NUMBER_UNIT = re.compile(r"^[\d\s.,?%°/+-]*(?:ml|l|g|kg|mg)?$", re.I)
_SKU_SUFFIX = re.compile(r"\s+\d+(?:[.,]\d+)?\s*(?:ml|l|g|kg)\b$", re.I)

_GENERIC_LABELS = {
    "still water", "sparkling water", "flavoured beverage", "flavored beverage",
    "fermented dairy", "plant based drinks", "fermented plant based",
    "dairy drinks", "non-dairy creamer", "non dairy creamer",
    "dairy / plant based dessert", "dairy/plant based dessert",
    "powdered specialized nutrition", "liquid specialized nutrition",
    "crème specialized nutrition", "creme specialized nutrition",
    "baby cereal", "meat and fish based wet products", "fruit and veg based wet products",
    "summary", "type", "workshop", "screening", "training", "individual", "total",
    "no", "unit", "qty", "sample", "samples", "control", "description",
}


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text.replace("\v", " ").replace("\r", " ").replace("\n", " ")).strip()


def _group_key(element: TextElement) -> tuple[int, tuple[int, ...]]:
    path = element.shape_path or ((element.shape_id or -1),)
    return element.slide_index, tuple(path)


def _looks_like_brand_candidate(text: str) -> bool:
    clean = _norm(text).strip(" |")
    if not clean or len(clean) > 90 or clean.endswith(":"):
        return False
    low = clean.casefold()
    if low in _GENERIC_LABELS or _BRANDS_CUE.search(clean) or _BRAND_HEADER.search(clean):
        return False
    if _ONLY_NUMBER_UNIT.fullmatch(clean):
        return False
    words = _WORD.findall(clean)
    if not words or len(words) > 7:
        return False
    # Sentences/instructions are not brand candidates.
    if any(mark in clean for mark in (".", "?", "!", ";")) and not re.search(r"\b\d+(?:\.\d+)?\s*(?:ml|l|g|kg)\b", clean, re.I):
        return False
    titleish = sum(1 for w in words if w[:1].isupper() or any(c.isupper() for c in w[1:]))
    return titleish / len(words) >= 0.60




def _add_entity_with_safe_base(entities: set[str], text: str) -> None:
    clean = _norm(text).strip(" |")
    if not _looks_like_brand_candidate(clean):
        return
    entities.add(clean)
    # Product slides often append pack size to a brand/product variant. Add the
    # size-free variant as an inline protection key without reducing arbitrary
    # multiword names to a single generic word.
    base = _SKU_SUFFIX.sub("", clean).strip()
    if base != clean and _looks_like_brand_candidate(base):
        entities.add(base)


def detect_brand_entities(
    *,
    elements_by_slide: dict[int, list[TextElement]],
    titles: dict[int, TextElement | None],
    persistent_preserve: set[str],
) -> set[str]:
    """Detect auditable product/brand entities from explicit presentation context.

    We intentionally do not label every Title Case phrase as a brand. Candidates are
    collected only when the slide/table explicitly identifies brand/product content.
    """
    entities = {text for text in persistent_preserve if text.strip()}

    # Slides explicitly labelled with e.g. "Brands | Danone".
    for slide_index, rows in elements_by_slide.items():
        cue_rows = [row for row in rows if _BRANDS_CUE.search(_norm(row.text))]
        if not cue_rows:
            continue
        title = titles.get(slide_index)
        for cue in cue_rows:
            clean = _norm(cue.text)
            parts = [p.strip() for p in clean.split("|") if p.strip()]
            if len(parts) >= 2 and _looks_like_brand_candidate(parts[-1]):
                _add_entity_with_safe_base(entities, parts[-1])
        for row in rows:
            if row is title:
                continue
            clean = _norm(row.text)
            if _looks_like_brand_candidate(clean):
                _add_entity_with_safe_base(entities, clean)

    # Tables explicitly containing a Product/Brand Name column.
    table_groups: dict[tuple[int, tuple[int, ...]], list[TextElement]] = defaultdict(list)
    for rows in elements_by_slide.values():
        for row in rows:
            if row.kind == "table_cell" and row.column is not None and row.row is not None:
                table_groups[_group_key(row)].append(row)

    for rows in table_groups.values():
        headers = [row for row in rows if _BRAND_HEADER.search(_norm(row.text))]
        for header in headers:
            for row in rows:
                if row.column != header.column or row.row is None or header.row is None or row.row <= header.row:
                    continue
                clean = _norm(row.text)
                if _looks_like_brand_candidate(clean):
                    _add_entity_with_safe_base(entities, clean)

    return entities
