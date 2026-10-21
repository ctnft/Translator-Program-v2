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
    _pattern = re.compile(
        r"https?://\S+|www\.\S+|"
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b|"
        r"(?i:\b[A-Za-z0-9.-]+\.(?:com|org|net|id|co\.id)\b)|"
        r"\b(?:[A-Z][a-z]?\d*){2,}\b|"
        r"\bpH\b|"
        r"\b[A-Z][A-Z0-9_-]{1,}\b|"
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
