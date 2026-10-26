from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ProtectedText:
    text: str
    mapping: dict[str, str]

    def restore(self, translated: str) -> str:
        result = translated
        missing: dict[str, list[str]] = {}
        for token, original in self.mapping.items():
            if token in result:
                result = result.replace(token, original)
            else:
                missing.setdefault(original, []).append(token)

        # full_element_text exposes the original protected literals to the model.
        # If the model reproduces the literal directly instead of the token, that
        # is still safe. Require the correct occurrence count so a truly dropped
        # number/formula/code is never silently accepted.
        folded = result.casefold()
        for original, tokens in missing.items():
            literal_count = folded.count(original.casefold()) if original else 0
            if literal_count < len(tokens):
                raise ValueError(f"Protected token hilang dari hasil translation: {tokens[0]}")
        return result


class ProtectedSpanEngine:
    """Protect only spans that are truly immutable.

    Phase 5.1.6.10 deliberately removes the old broad chemical/acronym pattern
    because it misclassified ordinary acronyms such as ``SKU`` / ``SKUs`` as
    chemistry and could make an entire textbox fail validation.

    Brands and approved acronyms are handled by document-intelligence / terminology
    preserve locks. This layer protects deterministic values that must survive
    translation byte-for-byte: URLs, e-mail/domain names, structured document codes,
    formula-like tokens, pH, and numbers/units.
    """

    _pattern = re.compile(
        r"https?://\S+|www\.\S+|"
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|"
        r"(?i:\b[A-Za-z0-9.-]+\.(?:com|org|net|id|co\.id)\b)|"
        # Structured document/protocol identifiers such as QFS-AE-SPT-013.
        r"\b[A-Z]{2,}(?:-[A-Z0-9]{2,}){2,}\b|"
        # Formula-like tokens with an explicit digit: CO2, H2O, FeCl3.
        # Requiring a digit prevents SKU/SKUs from being classified as chemistry.
        r"\b(?=[A-Za-z0-9]*\d)(?:[A-Z][a-z]?\d*){2,}\b|"
        # Conventional mixed-case formula without a digit, e.g. NaCl.
        r"\b(?:[A-Z][a-z]){2,}\b|"
        r"\bpH\b|"
        r"(?<!\w)[+-]?\d+(?:[.,]\d+)*(?:\s*(?:%|°C|°F|mg|kg|g|µg|ug|mL|ml|L|s|min|h|hr|rpm|kPa|MPa|Pa|bar|ppm|ppb|Hz|kHz|MHz))?(?!\w)"
    )

    def protect(self, text: str) -> ProtectedText:
        mapping: dict[str, str] = {}
        counter = 0

        def repl(match: re.Match[str]) -> str:
            nonlocal counter
            value = match.group(0)
            counter += 1
            token = f"__PROTECTED_{counter:04d}__"
            mapping[token] = value
            return token

        return ProtectedText(self._pattern.sub(repl, text), mapping)
