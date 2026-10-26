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


    @staticmethod
    def _concept_tokens(text: str) -> list[str]:
        """Tokenize a terminology source for conservative concept matching.

        We intentionally keep semantic words such as ``based`` and ``plant``. Only
        punctuation is normalized. This lets ``Dairy Drinks`` match a source such as
        ``Dairy or Plant Based Drinks`` without making unrelated slide context valid.
        """
        return re.findall(r"[A-Za-z0-9]+", str(text or "").casefold())

    @classmethod
    def _concept_present(cls, source_text: str, terminology_source: str, *, max_gap: int = 4) -> bool:
        """Return True when terminology tokens occur in-order inside this source element.

        Exact phrase matching remains preferred. This relaxed path exists only for
        variants where the same concept is expanded by a few modifiers/conjunctions,
        e.g. ``Dairy Drinks`` inside ``Dairy or Plant Based Drinks``. It does *not*
        consult slide/document context.
        """
        needle = cls._concept_tokens(terminology_source)
        haystack = cls._concept_tokens(source_text)
        if not needle or not haystack:
            return False
        if len(needle) == 1:
            return needle[0] in haystack

        start = 0
        while start < len(haystack):
            try:
                pos = haystack.index(needle[0], start)
            except ValueError:
                return False
            prev = pos
            matched = True
            for token in needle[1:]:
                found = None
                upper = min(len(haystack), prev + max_gap + 2)
                for idx in range(prev + 1, upper):
                    if haystack[idx] == token:
                        found = idx
                        break
                if found is None:
                    matched = False
                    break
                prev = found
            if matched:
                return True
            start = pos + 1
        return False

    def validate_source_fidelity(self, source: str, target: str) -> list[str]:
        """Reject glossary-target injection not justified by the current source element.

        The guard is source-local: slide/document context can disambiguate translation,
        but cannot authorize a glossary concept. Exact source phrases are counted first.
        If an exact phrase is absent, a conservative in-order concept match is accepted
        for expanded variants such as ``Dairy or Plant Based Drinks`` -> ``Minuman Susu
        atau Nabati``. This keeps the original protection against unrelated leakage such
        as ``Bitter`` -> ``Rasa Menyimpang``.
        """
        source_text = str(source or "")
        remaining_target = str(target or "")
        warnings: list[str] = []

        groups: dict[str, dict[str, object]] = {}
        fidelity_terms = [
            t for t in self.terms
            if str(t.get("status", "")).strip().lower() in {"locked", "approved"}
        ]
        for term in fidelity_terms:
            src = str(term.get("source", "")).strip()
            tgt = str(term.get("target", "")).strip()
            if not src or not tgt:
                continue
            key = tgt.casefold()
            group = groups.setdefault(key, {"target": tgt, "sources": []})
            group["sources"].append(src)

        # Longest targets first so a longer regulatory phrase does not also trigger
        # a shorter target nested inside it (e.g. "Minuman Susu" inside a longer term).
        ordered = sorted(groups.values(), key=lambda g: len(str(g["target"])), reverse=True)
        for group in ordered:
            target_phrase = str(group["target"])
            sources = sorted(set(group["sources"]), key=len, reverse=True)
            target_pattern = re.compile(r"(?<!\w)" + re.escape(target_phrase) + r"(?!\w)", re.I)
            target_matches = list(target_pattern.finditer(remaining_target))
            if not target_matches:
                continue

            source_alt = "|".join(re.escape(item) for item in sources)
            source_pattern = re.compile(r"(?<!\w)(?:" + source_alt + r")(?!\w)", re.I)
            exact_source_count = len(list(source_pattern.finditer(source_text)))

            # When an approved target arises from a semantically expanded source phrase,
            # allow one occurrence if at least one of its source aliases is present as a
            # conservative in-order token concept. This fixes false positives without
            # allowing slide-context terminology leakage.
            concept_source_count = 0
            if exact_source_count == 0 and any(
                self._concept_present(source_text, item) for item in sources
            ):
                concept_source_count = 1

            source_count = max(exact_source_count, concept_source_count)
            target_count = len(target_matches)
            if target_count > source_count:
                warnings.append(
                    f"terminology_injection:{target_phrase}:target={target_count}:source={source_count}"
                )

            # Mask this target phrase before checking shorter target phrases.
            remaining_target = target_pattern.sub(lambda m: " " * len(m.group(0)), remaining_target)

        return warnings

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
