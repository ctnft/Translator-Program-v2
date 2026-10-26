from __future__ import annotations

import re
from dataclasses import dataclass


_BREAK_RE = re.compile(r"\r|\v|\n")
_TOKEN_RE = re.compile(r"__PPT_BREAK_(\d{4})__")


@dataclass(frozen=True)
class SemanticTextBlock:
    """A PowerPoint text element encoded as one semantic translation unit.

    PowerPoint often uses paragraph/soft line breaks to carry presentation layout
    and per-line formatting. Those boundaries are layout metadata, not independent
    translation units. We replace them with immutable markers while the LLM
    translates the whole element, then restore the exact original break characters.
    """

    source_text: str
    encoded_text: str
    flattened_text: str
    break_tokens: tuple[str, ...]
    break_values: tuple[str, ...]
    line_segments: tuple[str, ...]

    @classmethod
    def encode(cls, text: str) -> "SemanticTextBlock":
        tokens: list[str] = []
        values: list[str] = []
        segments: list[str] = []
        pieces: list[str] = []
        last = 0

        for index, match in enumerate(_BREAK_RE.finditer(text), start=1):
            token = f"__PPT_BREAK_{index:04d}__"
            segment = text[last : match.start()]
            pieces.append(segment)
            segments.append(segment)
            pieces.append(f" {token} ")
            tokens.append(token)
            values.append(match.group(0))
            last = match.end()
        tail = text[last:]
        pieces.append(tail)
        segments.append(tail)

        flattened = _BREAK_RE.sub(" ", text)
        flattened = re.sub(r"\s+", " ", flattened).strip()

        return cls(
            source_text=text,
            encoded_text="".join(pieces),
            flattened_text=flattened,
            break_tokens=tuple(tokens),
            break_values=tuple(values),
            line_segments=tuple(segments),
        )

    @property
    def break_count(self) -> int:
        return len(self.break_tokens)

    def decode(self, translated: str) -> str:
        result = translated

        # Every layout boundary must survive exactly once and in original order.
        positions: list[int] = []
        for token in self.break_tokens:
            count = result.count(token)
            if count != 1:
                raise ValueError(
                    f"Marker line-break {token} harus muncul tepat sekali; ditemukan {count}."
                )
            positions.append(result.index(token))
        if positions != sorted(positions):
            raise ValueError("Urutan marker line-break berubah pada hasil translation.")

        unexpected = [
            f"__PPT_BREAK_{match.group(1)}__"
            for match in _TOKEN_RE.finditer(result)
            if f"__PPT_BREAK_{match.group(1)}__" not in self.break_tokens
        ]
        if unexpected:
            raise ValueError(f"Marker line-break tak dikenal pada hasil: {unexpected}")

        for token, value in zip(self.break_tokens, self.break_values):
            # Spaces were deliberately added around the marker for the LLM. Strip
            # only spaces/tabs immediately adjacent to the marker so the restored
            # PowerPoint paragraph boundary does not gain artificial whitespace.
            result = re.sub(rf"[ \t]*{re.escape(token)}[ \t]*", value, result, count=1)
        return result
