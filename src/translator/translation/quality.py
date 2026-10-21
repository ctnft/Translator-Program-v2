from __future__ import annotations

import re
from dataclasses import dataclass, field


_NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|°C|°F|mg|kg|g|µg|ug|mL|ml|L|s|min|h|hr|rpm|kPa|MPa|Pa|bar|ppm|ppb|Hz|kHz|MHz))?(?!\w)")
_URL = re.compile(r"https?://\S+|www\.\S+|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", re.I)
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass
class QualityAssessment:
    valid: bool = True
    ambiguous: bool = False
    warnings: list[str] = field(default_factory=list)


class TranslationQualityValidator:
    """Cheap deterministic validation before writing translated text to PowerPoint."""

    def assess(
        self,
        *,
        source: str,
        target: str,
        semantic_role: str = "body",
        ambiguous_hint: bool = False,
        preserve_phrases: tuple[str, ...] = (),
    ) -> QualityAssessment:
        warnings: list[str] = []
        valid = True

        if not target.strip():
            return QualityAssessment(valid=False, warnings=["empty_target"])

        if source.strip() == target.strip():
            warnings.append("no_change")

        source_numbers = _NUMBER.findall(source)
        target_numbers = _NUMBER.findall(target)
        if source_numbers != target_numbers:
            valid = False
            warnings.append("numeric_or_unit_mismatch")

        source_urls = _URL.findall(source)
        target_urls = _URL.findall(target)
        if source_urls != target_urls:
            valid = False
            warnings.append("url_or_email_mismatch")

        for phrase in preserve_phrases:
            if phrase and phrase.casefold() in source.casefold() and phrase.casefold() not in target.casefold():
                valid = False
                warnings.append(f"preserve_phrase_missing:{phrase}")

        source_words = [w.casefold() for w in _WORD.findall(source)]
        target_words = [w.casefold() for w in _WORD.findall(target)]
        shared_english = set(source_words) & set(target_words)
        if source_words and len(shared_english) / max(1, len(set(source_words))) >= 0.75:
            if source.strip() != target.strip():
                warnings.append("high_source_word_retention")

        if semantic_role == "slide_title":
            source_count = max(1, len(source_words))
            target_count = max(1, len(target_words))
            if target_count > max(12, source_count * 3):
                warnings.append("title_expansion_suspicious")

        ambiguous = ambiguous_hint or any(
            warning in {"no_change", "high_source_word_retention", "title_expansion_suspicious"}
            for warning in warnings
        )
        return QualityAssessment(valid=valid, ambiguous=ambiguous, warnings=warnings)
