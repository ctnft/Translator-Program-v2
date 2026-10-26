from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any

from .models import WordDocumentStats, WordElement
from .walker import WordWalker

_SPACE = re.compile(r"\s+")
_BRANDS_CUE = re.compile(r"\bbrands?\s*\|\s*(.+)$", re.I)
_BRAND_HEADER = re.compile(r"\b(?:product\s*/?\s*brand\s*name|brand\s*name|merek)\b", re.I)
_WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ0-9'&.+/-]*")

_ONLY_URL_EMAIL = re.compile(r"^(?:https?://\S+|www\.\S+|[^\s@]+@[^\s@]+\.[^\s@]+)$", re.I)
_VALUE_UNIT_ONLY = re.compile(
    r"^\s*[~≈<>≤≥+\-]?\s*\d+(?:[.,]\d+)?(?:\s*[x×]\s*\d+(?:[.,]\d+)?){0,3}\s*"
    r"(?:%|mm(?:²|2|³|3)?|cm(?:²|2|³|3)?|m(?:²|2|³|3)?|km|mg|g|kg|t|ton|ml|mL|l|L|"
    r"Pa|kPa|MPa|GPa|N|kN|V|kV|A|kA|W|kW|MW|VA|kVA|Hz|°C|deg|day|days|hari)?\s*$",
    re.I,
)
_TIME_DATE_ONLY = re.compile(
    r"^\s*(?:\d{1,2}[:.]\d{2}(?:\s*(?:WIB|WITA|WIT|AM|PM))?|"
    r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\s*$",
    re.I,
)
_INDONESIAN_HINTS = {
    "yang", "dan", "atau", "untuk", "dari", "dengan", "pada", "dalam", "tidak", "harus", "dapat", "akan",
    "sebagai", "sesuai", "terhadap", "oleh", "serta", "pekerjaan", "pembangunan", "pengadaan", "dokumen", "surat",
    "perusahaan", "proyek", "pelaksanaan", "biaya", "nilai", "peserta", "penawaran", "teknis", "administrasi",
    "material", "bangunan", "struktur", "beton", "baja", "lokasi", "area", "jalan", "tanah", "jadwal", "persyaratan",
    "kontrak", "pemilik", "konsultan", "kontraktor", "minimum", "maksimum", "sistem", "pekerja", "peralatan", "metode",
    "surat", "jaminan", "harga", "waktu", "pelaksana", "lapangan", "gambar", "fondasi", "kolom", "balok", "pelat",
}
_ENGLISH_HINTS = {
    "the", "and", "or", "for", "from", "with", "to", "of", "in", "on", "is", "are", "was", "were", "be", "been",
    "must", "shall", "should", "may", "will", "not", "document", "documents", "work", "construction", "building",
    "project", "contract", "owner", "contractor", "consultant", "technical", "price", "schedule", "material", "design",
    "requirements", "requirement", "submission", "equipment", "system", "site", "structure", "structural", "concrete",
}


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text.replace("\v", " ").replace("\r", " ").replace("\n", " ")).strip()


def _brand_candidate(text: str) -> bool:
    clean = _norm(text).strip(" |")
    if not clean or len(clean) > 90 or clean.endswith(":"):
        return False
    words = _WORD.findall(clean)
    if not words or len(words) > 7:
        return False
    if any(mark in clean for mark in (".", "?", "!", ";")):
        return False
    titleish = sum(1 for w in words if w[:1].isupper() or any(c.isupper() for c in w[1:]))
    return titleish / len(words) >= 0.60



def _smart_preserve_reason(text: str) -> str:
    """Return a deterministic skip reason for Word elements that do not need EN→ID translation.

    This intentionally prefers false negatives (translate a little extra) over false positives
    (silently leave meaningful English prose untranslated).
    """
    clean = _norm(text).strip()
    if not clean:
        return "smart_skip_empty"
    if not any(ch.isalpha() for ch in clean):
        return "smart_skip_nonlinguistic"
    if _ONLY_URL_EMAIL.fullmatch(clean):
        return "smart_skip_url_email"
    if _TIME_DATE_ONLY.fullmatch(clean):
        return "smart_skip_time_date"
    if _VALUE_UNIT_ONLY.fullmatch(clean):
        return "smart_skip_value_unit"

    # Pure identifier/document-code cells such as QFS-AE-SPT-013, C-0501B, Rev-02.
    # Require at least one digit or a separator so ordinary all-caps words stay translatable.
    compact = clean
    letters = "".join(ch for ch in compact if ch.isalpha())
    if (
        len(clean) <= 64
        and not re.search(r"\s", clean)
        and re.fullmatch(r"[A-Za-z0-9_.:/+\-]+", compact)
        and letters
        and (
            any(ch.isdigit() for ch in compact)
            or (any(ch in "_./:+-" for ch in compact) and letters.upper() == letters)
        )
    ):
        return "smart_skip_identifier"

    # Conservative target-language detection. Only skip longer text when Indonesian
    # vocabulary clearly dominates and there is no strong English signal.
    words = [w.casefold() for w in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", clean)]
    if len(words) >= 5:
        id_hits = sum(w in _INDONESIAN_HINTS for w in words)
        en_hits = sum(w in _ENGLISH_HINTS for w in words)
        if id_hits >= 3 and en_hits == 0 and id_hits / max(1, len(words)) >= 0.45:
            return "smart_skip_already_indonesian"
    return ""


@dataclass
class WordElementIntelligence:
    element_key: str
    semantic_role: str
    translate_policy: str = "translate"
    context_key: str = ""
    ambiguous: bool = False
    reasons: list[str] = field(default_factory=list)
    protected_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WordDocumentProfile:
    document_type: str = "technical_document"
    subject: str = "food_science"
    title: str = ""
    organizations: list[str] = field(default_factory=list)
    brand_entities: list[str] = field(default_factory=list)
    preserve_phrases: list[str] = field(default_factory=list)
    style: str = (
        "Bahasa Indonesia profesional, natural, komunikatif, sesuai konteks dokumen teknis; "
        "gunakan istilah food science/sensory yang disetujui dan pertahankan brand/identifier."
    )

    def summary(self) -> str:
        return (
            f"document_type={self.document_type}; subject={self.subject}; title={self.title or 'unknown'}; "
            f"organizations={', '.join(self.organizations[:8]) or 'unknown'}; "
            f"brand_entities={', '.join(self.brand_entities[:30]) or 'unknown'}; style={self.style}"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WordAnalysis:
    profile: WordDocumentProfile
    elements: dict[str, WordElementIntelligence]
    warnings: list[str] = field(default_factory=list)
    version: str = "phase522-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile.to_dict(),
            "elements": {k: v.to_dict() for k, v in self.elements.items()},
            "warnings": list(self.warnings),
        }


class WordDocumentAnalyzer:
    def analyze(
        self,
        stats: WordDocumentStats,
        elements: list[WordElement],
        *,
        domain: str | None = None,
        style: str | None = None,
        smart_eligibility: bool = True,
    ) -> WordAnalysis:
        title = ""
        for element in sorted(elements, key=lambda e: (e.range_start if e.range_start is not None else 10**12)):
            if element.story != "main":
                continue
            style_name_cf = element.style_name.casefold()
            if (element.outline_level == 1 or "title" in style_name_cf or "judul" in style_name_cf) and element.text.strip():
                title = _norm(element.text)
                break
        if not title:
            for element in elements:
                if element.story == "main" and element.text.strip():
                    title = _norm(element.text)[:240]
                    break

        brand_entities = self._detect_brands(elements)
        repeated_hf = Counter(
            _norm(e.text) for e in elements if e.kind in {"header", "footer"} and _norm(e.text)
        )
        for text, count in repeated_hf.items():
            if count >= 2 and _brand_candidate(text):
                brand_entities.add(text)

        organizations = sorted(brand_entities)[:20]
        preserve = sorted(brand_entities, key=lambda x: (-len(x), x.casefold()))
        profile = WordDocumentProfile(
            subject=(domain or "food_science"),
            title=title,
            organizations=organizations,
            brand_entities=sorted(brand_entities),
            preserve_phrases=preserve,
            style=(style or "Bahasa Indonesia profesional, natural, komunikatif, sesuai konteks dokumen teknis; pertahankan istilah teknis, brand, identifier, angka, formula, dan unit."),
        )

        intelligence: dict[str, WordElementIntelligence] = {}
        preserve_cf = {p.casefold() for p in preserve}
        for element in elements:
            key = WordWalker.element_key(element)
            role = self._semantic_role(element)
            reasons: list[str] = []
            policy = "translate"
            clean = _norm(element.text)
            if element.has_fields:
                policy = "preserve"
                reasons.append("contains_word_field")
            elif element.has_content_controls:
                policy = "preserve"
                reasons.append("contains_content_control")
            elif clean.casefold() in preserve_cf:
                policy = "preserve"
                role = "brand_entity" if element.kind not in {"header", "footer"} else role
                reasons.append("document_brand_entity")
            elif smart_eligibility:
                smart_reason = _smart_preserve_reason(clean)
                if smart_reason:
                    policy = "preserve"
                    reasons.append(smart_reason)

            protected = [p for p in preserve if re.search(r"(?<!\w)" + re.escape(p) + r"(?!\w)", element.text, re.I)]
            context_payload = {
                "kind": element.kind,
                "story": element.story,
                "style": element.style_name,
                "heading_path": list(element.heading_path),
                "table": [element.table_index, element.row, element.column],
            }
            context_key = hashlib.sha256(
                json.dumps(context_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            intelligence[key] = WordElementIntelligence(
                element_key=key,
                semantic_role=role,
                translate_policy=policy,
                context_key=context_key,
                ambiguous=role in {"heading", "table_cell"} and len(clean.split()) <= 4,
                reasons=reasons,
                protected_entities=protected,
            )

        return WordAnalysis(profile=profile, elements=intelligence, warnings=list(stats.warnings))

    @staticmethod
    def _semantic_role(element: WordElement) -> str:
        if element.kind == "table_cell":
            return "table_cell"
        if element.kind in {"header", "footer"}:
            return element.kind
        if element.kind == "textbox":
            return "textbox"
        if element.outline_level is not None and 1 <= element.outline_level <= 9:
            return "heading"
        style = element.style_name.casefold()
        if "heading" in style or "judul" in style or style == "title":
            return "heading"
        return "body"

    @staticmethod
    def _detect_brands(elements: list[WordElement]) -> set[str]:
        brands: set[str] = set()
        for e in elements:
            match = _BRANDS_CUE.search(_norm(e.text))
            if match and _brand_candidate(match.group(1)):
                brands.add(match.group(1).strip())

        tables: dict[int, list[WordElement]] = defaultdict(list)
        for e in elements:
            if e.kind == "table_cell" and e.table_index is not None:
                tables[e.table_index].append(e)
        for cells in tables.values():
            headers = [c for c in cells if _BRAND_HEADER.search(_norm(c.text)) and c.column is not None]
            for header in headers:
                for cell in cells:
                    if cell.column == header.column and cell.row and header.row and cell.row > header.row:
                        if _brand_candidate(cell.text):
                            brands.add(_norm(cell.text))
        return brands
