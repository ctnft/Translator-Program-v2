import re
from dataclasses import dataclass


@dataclass
class LockedText:
    text: str
    mapping: dict[str, str]

    def restore(self, translated: str) -> str:
        result = translated
        missing: dict[str, list[str]] = {}
        for token, target in self.mapping.items():
            if token in result:
                result = result.replace(token, target)
            else:
                missing.setdefault(target, []).append(token)

        # Some local models copy the locked literal from full_element_text instead
        # of the opaque token. Accept that only when enough literal occurrences
        # are present; otherwise fail and let the translation engine retry.
        folded = result.casefold()
        for target, tokens in missing.items():
            literal_count = folded.count(target.casefold()) if target else 0
            if literal_count < len(tokens):
                raise ValueError(f"Locked terminology token hilang: {tokens[0]}")
        return result


class TerminologyLock:
    def __init__(self, terms):
        normalized = []
        for raw in terms:
            term = dict(raw)
            status = str(term.get("status", "")).strip().lower()
            if status == "preserve_locked" and not term.get("target"):
                term["target"] = term.get("source")
            normalized.append(term)
        self.terms = sorted(normalized, key=lambda x: len(str(x.get("source", ""))), reverse=True)

    def _locked_terms(self):
        return [
            t for t in self.terms
            if t.get("status") == "locked" or t.get("locked") is True
        ]

    def _preserve_terms(self):
        return [t for t in self.terms if t.get("status") == "preserve_locked"]

    def should_preserve(self, text: str) -> bool:
        stripped = text.strip().casefold()
        return any(
            stripped == str(term.get("source", "")).strip().casefold()
            for term in self._preserve_terms()
        )

    def apply(self, text):
        result = text
        for term in self._locked_terms():
            pattern = r"(?<!\w)" + re.escape(term["source"]) + r"(?!\w)"
            result = re.sub(pattern, term["target"], result, flags=re.IGNORECASE)
        return result

    def exact_target(self, text):
        stripped = text.strip()
        for term in self._locked_terms():
            if stripped.casefold() == str(term["source"]).strip().casefold():
                return str(term["target"])
        return None

    def relevant_guidance(self, text: str, *, limit: int = 24) -> list[dict[str, str]]:
        """Return only glossary rows relevant to the current semantic context.

        This is prompt guidance, not the enforcement layer. Exact locked phrases are
        still token-protected before inference, so the model cannot silently replace
        an approved regulatory/SNI term with its own synonym.
        """
        haystack = str(text or "")
        rows: list[dict[str, str]] = []
        for term in self._locked_terms():
            source = str(term.get("source", "")).strip()
            if not source:
                continue
            if re.search(r"(?<!\w)" + re.escape(source) + r"(?!\w)", haystack, re.I):
                row = {
                    "source": source,
                    "target": str(term.get("target", "")),
                }
                if term.get("authority"):
                    row["authority"] = str(term["authority"])
                if term.get("reference"):
                    row["reference"] = str(term["reference"])
                rows.append(row)
                if len(rows) >= max(1, int(limit)):
                    break
        return rows

    def protect_for_llm(self, text):
        result = text
        mapping = {}
        index = 0
        # Preserve locks are applied before translation locks. They restore to the
        # exact source phrase and are never translated.
        all_terms = [
            (term, str(term.get("source", ""))) for term in self._preserve_terms()
        ] + [
            (term, str(term.get("target", ""))) for term in self._locked_terms()
        ]
        for term, restore_value in all_terms:
            source = str(term.get("source", ""))
            if not source:
                continue
            pattern = re.compile(r"(?<!\w)" + re.escape(source) + r"(?!\w)", re.IGNORECASE)
            while True:
                match = pattern.search(result)
                if match is None:
                    break
                index += 1
                token = f"__TERM_{index:04d}__"
                mapping[token] = restore_value
                result = result[:match.start()] + token + result[match.end():]
        return LockedText(result, mapping)
