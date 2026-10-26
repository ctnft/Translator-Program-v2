from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ElementIntelligence:
    element_key: str
    slide_index: int
    source_text: str
    semantic_role: str = "body"
    translate_policy: str = "translate"
    position_bucket: str = "unknown"
    repetition_count: int = 1
    repetition_ratio: float = 0.0
    position_consistency: float = 0.0
    confidence: float = 0.5
    ambiguous: bool = False
    reasons: list[str] = field(default_factory=list)
    context_key: str = ""
    protected_entities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SlideIntelligence:
    slide_index: int
    title: str = ""
    slide_role: str = "content"
    body_text: list[str] = field(default_factory=list)
    previous_title: str = ""
    next_title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DocumentProfile:
    document_type: str = "technical_presentation"
    subject: str = "food_science"
    title: str = ""
    organizations: list[str] = field(default_factory=list)
    brand_entities: list[str] = field(default_factory=list)
    preserve_phrases: list[str] = field(default_factory=list)
    repeated_phrases: list[dict[str, Any]] = field(default_factory=list)
    style: str = (
        "Bahasa Indonesia profesional, natural, komunikatif, sesuai konteks presentasi; "
        "hindari terjemahan kata-per-kata dan pertahankan istilah teknis yang disetujui."
    )

    def summary(self) -> str:
        orgs = ", ".join(self.organizations[:8]) or "unknown"
        brands = ", ".join(self.brand_entities[:20]) or "unknown"
        return (
            f"document_type={self.document_type}; subject={self.subject}; "
            f"document_title={self.title or 'unknown'}; organizations={orgs}; "
            f"brand_entities={brands}; style={self.style}"
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeckAnalysis:
    profile: DocumentProfile
    slides: dict[int, SlideIntelligence]
    elements: dict[str, ElementIntelligence]
    warnings: list[str] = field(default_factory=list)
    version: str = "phase51611-v1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "profile": self.profile.to_dict(),
            "slides": {str(k): v.to_dict() for k, v in sorted(self.slides.items())},
            "elements": {k: v.to_dict() for k, v in self.elements.items()},
            "warnings": list(self.warnings),
        }
