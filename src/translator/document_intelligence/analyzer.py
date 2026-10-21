from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from typing import Iterable

from translator.powerpoint_com.models import PresentationStats, TextElement
from translator.powerpoint_com.walker import PowerPointWalker
from .models import DeckAnalysis, DocumentProfile, ElementIntelligence, SlideIntelligence
from .brand_entities import detect_brand_entities


_SPACE = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'&.-]*")
_URLISH = re.compile(r"(?:https?://|www\.|\.(?:com|org|net|id|co\.id)\b|@)", re.I)

# Repeated labels in these families should not be auto-preserved merely because
# they occur on many slides. They are ordinary translatable presentation language.
_COMMON_TRANSLATABLE = {
    "confidential", "training", "trainer", "day", "page", "module", "agenda",
    "objective", "objectives", "safety", "housekeeping", "rules", "opening",
    "closing", "participant", "participants", "introduction", "expectation",
    "expectations", "practice", "practices", "session", "sessions", "overview",
    "contents", "content", "thank you", "questions", "question", "sensory",
}

_TITLE_AMBIGUITY_WORDS = {
    "safety", "housekeeping", "greetings", "greeting", "induction", "panel",
    "session", "opening", "closing", "handling", "quality", "control", "trainer",
    "expectation", "expectations", "practice", "practices", "facility", "assessment",
    "evaluation", "sample", "sampling", "briefing", "orientation", "review",
}


def _norm(text: str) -> str:
    return _SPACE.sub(" ", text.replace("\v", " ").replace("\r", " ").replace("\n", " ")).strip()


def _norm_key(text: str) -> str:
    return _norm(text).casefold()


def _words(text: str) -> list[str]:
    return _WORD.findall(_norm(text))


def _safe_ratio(value: float | None, total: float | None) -> float | None:
    if value is None or total in (None, 0):
        return None
    return max(0.0, min(1.0, float(value) / float(total)))


class DocumentIntelligenceAnalyzer:
    """Deterministic full-deck pre-analysis for context-aware translation.

    This layer intentionally does not use an LLM. It derives document signals from
    repetition, geometry, typography, slide neighborhood, and text structure so the
    actual translator receives auditable context instead of isolated strings.
    """

    def __init__(
        self,
        *,
        repeat_ratio_threshold: float = 0.35,
        repeat_min_slides: int = 3,
        position_consistency_threshold: float = 0.70,
    ):
        self.repeat_ratio_threshold = repeat_ratio_threshold
        self.repeat_min_slides = repeat_min_slides
        self.position_consistency_threshold = position_consistency_threshold
        self.walker = PowerPointWalker()

    def analyze(
        self,
        stats: PresentationStats,
        elements: list[TextElement],
    ) -> DeckAnalysis:
        slide_count = max(1, stats.slide_count)
        slide_width, slide_height = self._dimensions(stats, elements)

        elements_by_slide: dict[int, list[TextElement]] = defaultdict(list)
        occurrences: dict[str, list[TextElement]] = defaultdict(list)
        for element in elements:
            elements_by_slide[element.slide_index].append(element)
            key = _norm_key(element.text)
            if key:
                occurrences[key].append(element)

        repeat_info: dict[str, dict] = {}
        for key, rows in occurrences.items():
            unique_slides = {row.slide_index for row in rows}
            buckets = Counter(self._position_bucket(row, slide_width, slide_height) for row in rows)
            dominant_bucket, dominant_count = buckets.most_common(1)[0] if buckets else ("unknown", 0)
            repeat_info[key] = {
                "text": _norm(rows[0].text),
                "count": len(rows),
                "slide_count": len(unique_slides),
                "ratio": len(unique_slides) / slide_count,
                "dominant_position": dominant_bucket,
                "position_consistency": dominant_count / max(1, len(rows)),
            }

        titles: dict[int, TextElement | None] = {}
        for slide_index in range(1, stats.slide_count + 1):
            titles[slide_index] = self._detect_title(
                elements_by_slide.get(slide_index, []), slide_width, slide_height
            )

        # Track how often a phrase is actually used as a detected slide title.
        # A brand can legitimately become the title of one dedicated brand slide
        # while acting as a persistent header/footer on hundreds of other slides.
        # Therefore a boolean "appears as title anywhere" is too aggressive.
        title_occurrences = Counter(
            _norm_key(title.text)
            for title in titles.values()
            if title is not None and _norm(title.text)
        )
        persistent_preserve = self._detect_preserve_phrases(repeat_info, title_occurrences)
        brand_entities = detect_brand_entities(
            elements_by_slide=elements_by_slide,
            titles=titles,
            persistent_preserve=persistent_preserve,
        )
        preserve_phrases = set(persistent_preserve) | set(brand_entities)
        slides = self._build_slides(stats.slide_count, elements_by_slide, titles, preserve_phrases)
        profile = self._build_profile(
            slides, elements, repeat_info, persistent_preserve, brand_entities, preserve_phrases
        )

        element_intelligence: dict[str, ElementIntelligence] = {}
        for element in elements:
            key = self.walker.element_key(element)
            nkey = _norm_key(element.text)
            rep = repeat_info.get(nkey, {})
            title_el = titles.get(element.slide_index)
            is_title = title_el is element
            position = self._position_bucket(element, slide_width, slide_height)
            semantic_role, policy, reasons, confidence = self._classify_element(
                element=element,
                is_title=is_title,
                repeat=rep,
                persistent_preserve=persistent_preserve,
                brand_entities=brand_entities,
                position=position,
            )
            slide = slides[element.slide_index]
            ambiguous = self._is_ambiguous(element.text, semantic_role, slide.slide_role)
            context_key = self._context_key(
                profile=profile,
                semantic_role=semantic_role,
                slide_role=slide.slide_role,
                translate_policy=policy,
            )
            protected_entities = [
                entity for entity in profile.brand_entities
                if re.search(r"(?<!\w)" + re.escape(entity) + r"(?!\w)", element.text, re.I)
            ]
            element_intelligence[key] = ElementIntelligence(
                element_key=key,
                slide_index=element.slide_index,
                source_text=element.text,
                semantic_role=semantic_role,
                translate_policy=policy,
                position_bucket=position,
                repetition_count=int(rep.get("slide_count", 1)),
                repetition_ratio=round(float(rep.get("ratio", 0.0)), 4),
                position_consistency=round(float(rep.get("position_consistency", 0.0)), 4),
                confidence=round(confidence, 3),
                ambiguous=ambiguous,
                reasons=reasons,
                context_key=context_key,
                protected_entities=protected_entities,
            )

        return DeckAnalysis(profile=profile, slides=slides, elements=element_intelligence)

    @staticmethod
    def _dimensions(
        stats: PresentationStats, elements: Iterable[TextElement]
    ) -> tuple[float, float]:
        width = stats.slide_width
        height = stats.slide_height
        if not width:
            width = max(
                [((e.left or 0) + (e.width or 0)) for e in elements] or [960.0]
            )
        if not height:
            height = max(
                [((e.top or 0) + (e.height or 0)) for e in elements] or [540.0]
            )
        return max(float(width), 1.0), max(float(height), 1.0)

    @staticmethod
    def _position_bucket(element: TextElement, slide_width: float, slide_height: float) -> str:
        if element.left is None or element.top is None:
            return "unknown"
        cx = (element.left + (element.width or 0) / 2.0) / slide_width
        cy = (element.top + (element.height or 0) / 2.0) / slide_height
        horizontal = "left" if cx < 0.34 else ("right" if cx > 0.66 else "center")
        vertical = "top" if cy < 0.28 else ("bottom" if cy > 0.72 else "middle")
        return f"{vertical}_{horizontal}"

    def _detect_title(
        self, elements: list[TextElement], slide_width: float, slide_height: float
    ) -> TextElement | None:
        candidates = [e for e in elements if e.kind != "table_cell" and _norm(e.text)]
        if not candidates:
            return None
        font_sizes = [e.font_size for e in candidates if e.font_size and e.font_size > 0]
        max_font = max(font_sizes) if font_sizes else None

        def score(e: TextElement) -> float:
            words = len(_words(e.text))
            top_ratio = _safe_ratio(e.top, slide_height)
            points = 0.0
            # PowerPoint ppPlaceholderTitle=1 and ppPlaceholderCenterTitle=3.
            if e.placeholder_type in {1, 3}:
                points += 8.0
            if top_ratio is not None:
                if top_ratio < 0.18:
                    points += 3.0
                elif top_ratio < 0.38:
                    points += 1.5
            if e.font_size and max_font:
                ratio = e.font_size / max_font
                if ratio >= 0.95:
                    points += 4.0
                elif ratio >= 0.75:
                    points += 2.0
            if 1 <= words <= 12:
                points += 1.5
            if len(_norm(e.text)) <= 120:
                points += 0.5
            if e.bold:
                points += 0.5
            return points

        ranked = sorted(candidates, key=lambda e: (score(e), -(e.top or 99999)), reverse=True)
        best = ranked[0]
        # Require at least some visual/title-like evidence when geometry/font exists.
        return best if score(best) >= 2.0 else candidates[0]

    def _detect_preserve_phrases(
        self,
        repeat_info: dict[str, dict],
        title_occurrences: Counter[str],
    ) -> set[str]:
        preserve: set[str] = set()

        # Auto-preserve is intentionally conservative. Repetition alone is not
        # enough: repeated section titles and recurring instructional headings
        # must still be translated. Persistent branding is normally peripheral
        # to the slide body, so only stable edge/corner positions are eligible.
        branding_positions = {
            "bottom_left",
            "bottom_center",
            "bottom_right",
            "top_left",
            "top_right",
        }

        for key, info in repeat_info.items():
            text = str(info["text"])
            total_occurrences = max(1, int(info.get("count", 1)))
            title_count = int(title_occurrences.get(key, 0))
            title_share = title_count / total_occurrences

            # If the phrase is predominantly used as a slide title, it is
            # presentation content and must remain translatable.  Crucially, a
            # single dedicated brand slide must not cancel hundreds of stable
            # branding/header occurrences elsewhere in the deck.
            if title_share >= 0.50:
                continue

            if info["slide_count"] < self.repeat_min_slides:
                continue
            if info.get("dominant_position") not in branding_positions:
                continue

            strong_identifier = self._looks_like_strong_brand_identifier(text)
            normal_repetition = (
                info["ratio"] >= self.repeat_ratio_threshold
                and info["position_consistency"] >= self.position_consistency_threshold
            )
            strong_identifier_repetition = (
                strong_identifier
                and info["slide_count"] >= max(8, self.repeat_min_slides)
                and info["ratio"] >= 0.05
                and info["position_consistency"] >= 0.90
            )

            if not (normal_repetition or strong_identifier_repetition):
                continue
            if self._looks_like_brand(text):
                preserve.add(text)
        return preserve

    @staticmethod
    def _looks_like_strong_brand_identifier(text: str) -> bool:
        """Return True for identifiers that are much more brand/code-like than prose.

        This intentionally does not classify ordinary Title Case phrases as
        strong identifiers. It is used only to allow stable peripheral brands
        such as URL-like marks or all-caps identities to be preserved even when
        they occur in a smaller section of a very large deck.
        """
        clean = _norm(text)
        if not clean:
            return False
        if _URLISH.search(clean):
            return True
        letters = [c for c in clean if c.isalpha()]
        return len(letters) >= 5 and all(c.isupper() for c in letters)

    @staticmethod
    def _looks_like_brand(text: str) -> bool:
        clean = _norm(text)
        words = _words(clean)
        if not words:
            return False
        low = clean.casefold()
        if low in _COMMON_TRANSLATABLE:
            return False
        if _URLISH.search(clean):
            return True
        letters = [c for c in clean if c.isalpha()]
        if len(letters) >= 3 and all(c.isupper() for c in letters):
            return True
        title_words = [w for w in words if w[:1].isupper()]
        if len(words) >= 2 and len(title_words) / len(words) >= 0.8:
            # Repeated Title Case in a stable corner is a strong branding signal.
            return True
        return False

    def _build_slides(
        self,
        slide_count: int,
        elements_by_slide: dict[int, list[TextElement]],
        titles: dict[int, TextElement | None],
        preserve_phrases: set[str],
    ) -> dict[int, SlideIntelligence]:
        slides: dict[int, SlideIntelligence] = {}
        for slide_index in range(1, slide_count + 1):
            title_el = titles.get(slide_index)
            title = _norm(title_el.text) if title_el else ""
            body = []
            for element in elements_by_slide.get(slide_index, []):
                text = _norm(element.text)
                if not text or element is title_el or text in preserve_phrases:
                    continue
                body.append(text)
            role = self._slide_role(slide_index, title, body)
            slides[slide_index] = SlideIntelligence(
                slide_index=slide_index,
                title=title,
                slide_role=role,
                body_text=body[:30],
            )
        for slide_index, slide in slides.items():
            slide.previous_title = slides.get(slide_index - 1, SlideIntelligence(0)).title
            slide.next_title = slides.get(slide_index + 1, SlideIntelligence(0)).title
        return slides

    @staticmethod
    def _slide_role(slide_index: int, title: str, body: list[str]) -> str:
        low = title.casefold()
        if slide_index == 1:
            return "title_slide"
        if any(word in low for word in ("agenda", "module", "objective", "objectives", "contents")):
            return "agenda"
        if any(word in low for word in ("greeting", "greetings", "welcome", "opening")):
            return "opening_section"
        if any(word in low for word in ("safety", "housekeeping", "ground rule", "rules")):
            return "training_protocol"
        if any(word in low for word in ("summary", "conclusion", "closing", "thank")):
            return "closing_section"
        if len(body) <= 1 and title:
            return "section_title"
        return "content"

    def _build_profile(
        self,
        slides: dict[int, SlideIntelligence],
        elements: list[TextElement],
        repeat_info: dict[str, dict],
        persistent_preserve: set[str],
        brand_entities: set[str],
        preserve_phrases: set[str],
    ) -> DocumentProfile:
        all_text = " ".join(_norm(e.text).casefold() for e in elements)
        training_terms = sum(all_text.count(w) for w in (
            "training", "trainer", "participant", "participants", "agenda", "module", "expectation"
        ))
        document_type = "training_material" if training_terms >= 3 else "technical_presentation"

        if "sensory" in all_text:
            subject = "food_sensory_science"
        elif any(w in all_text for w in ("food", "shelf life", "water activity", "moisture")):
            subject = "food_science"
        else:
            subject = "technical_training"

        repeated = sorted(
            (
                {
                    "text": info["text"],
                    "slide_count": info["slide_count"],
                    "ratio": round(info["ratio"], 4),
                    "position": info["dominant_position"],
                    "position_consistency": round(info["position_consistency"], 4),
                }
                for info in repeat_info.values()
                if info["slide_count"] >= self.repeat_min_slides
            ),
            key=lambda item: (-item["slide_count"], item["text"].casefold()),
        )[:50]
        organizations = sorted(persistent_preserve, key=str.casefold)
        brands = sorted(brand_entities, key=str.casefold)
        title = slides.get(1, SlideIntelligence(1)).title
        return DocumentProfile(
            document_type=document_type,
            subject=subject,
            title=title,
            organizations=organizations,
            brand_entities=brands,
            preserve_phrases=sorted(preserve_phrases, key=str.casefold),
            repeated_phrases=repeated,
        )

    def _classify_element(
        self,
        *,
        element: TextElement,
        is_title: bool,
        repeat: dict,
        persistent_preserve: set[str],
        brand_entities: set[str],
        position: str,
    ) -> tuple[str, str, list[str], float]:
        text = _norm(element.text)
        reasons: list[str] = []
        if text in persistent_preserve:
            reasons.extend(["repeated_across_slides", "stable_position", "brand_like_text"])
            return "persistent_branding", "preserve", reasons, 0.95
        if text in brand_entities:
            reasons.extend(["brand_product_context", "brand_entity_exact_match"])
            return "brand_entity", "preserve", reasons, 0.96

        ratio = float(repeat.get("ratio", 0.0))
        consistency = float(repeat.get("position_consistency", 0.0))
        if ratio >= self.repeat_ratio_threshold and consistency >= self.position_consistency_threshold:
            if position.startswith("bottom_"):
                reasons.extend(["repeated_across_slides", "stable_bottom_position"])
                return "footer", "translate", reasons, 0.82
            if position.startswith("top_") and not is_title:
                reasons.extend(["repeated_across_slides", "stable_top_position"])
                return "header", "translate", reasons, 0.80

        if is_title:
            reasons.append("title_candidate_by_position_font")
            return "slide_title", "translate", reasons, 0.88
        if element.kind == "table_cell":
            return "table_cell", "translate", ["table_cell"], 0.98
        if element.kind == "group_text":
            return "group_text", "translate", ["grouped_shape_text"], 0.75
        return "body", "translate", ["ordinary_slide_text"], 0.70

    @staticmethod
    def _is_ambiguous(text: str, semantic_role: str, slide_role: str) -> bool:
        words = [w.casefold() for w in _words(text)]
        if semantic_role == "slide_title" and 1 <= len(words) <= 6:
            return True
        if slide_role in {"training_protocol", "opening_section", "section_title"} and len(words) <= 8:
            return True
        return any(w in _TITLE_AMBIGUITY_WORDS for w in words) and len(words) <= 8

    @staticmethod
    def _context_key(
        *, profile: DocumentProfile, semantic_role: str, slide_role: str, translate_policy: str
    ) -> str:
        payload = {
            "document_type": profile.document_type,
            "subject": profile.subject,
            "semantic_role": semantic_role,
            "slide_role": slide_role,
            "policy": translate_policy,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
