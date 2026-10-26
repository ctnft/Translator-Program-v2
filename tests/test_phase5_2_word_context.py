import json

from translator.word_com.intelligence import WordAnalysis, WordDocumentProfile, WordElementIntelligence
from translator.word_com.models import WordElement
from translator.word_com.translation_service import WordTranslationService
from translator.word_com.walker import WordWalker


def test_word_context_contains_heading_hierarchy_and_neighbors():
    element = WordElement(
        kind="paragraph",
        text="Prepare the samples.",
        paragraph_index=4,
        range_start=50,
        range_end=70,
        heading_path=("Sensory Training", "Sample Preparation"),
        style_name="Normal",
        page_number=3,
    )
    key = WordWalker.element_key(element)
    analysis = WordAnalysis(
        profile=WordDocumentProfile(title="Training Manual"),
        elements={key: WordElementIntelligence(key, "body", context_key="abc")},
    )
    payload = json.loads(
        WordTranslationService._context_payload(
            analysis,
            element,
            previous_text="Previous paragraph",
            next_text="Next paragraph",
            table_context=None,
        )
    )
    assert "document" not in payload  # document context is sent once by TranslationEngine
    assert payload["word_structure"]["heading_path"] == ["Sensory Training", "Sample Preparation"]
    assert payload["word_structure"]["previous_text"] == "Previous paragraph"
    assert payload["word_structure"]["next_text"] == "Next paragraph"


def test_word_context_is_compact_and_does_not_duplicate_full_element():
    element = WordElement(
        kind="paragraph", text="A" * 500, paragraph_index=1, range_start=0, range_end=500,
        heading_path=("H1", "H2"), style_name="Normal", page_number=1,
    )
    key = WordWalker.element_key(element)
    analysis = WordAnalysis(
        profile=WordDocumentProfile(title="X" * 1000),
        elements={key: WordElementIntelligence(key, "body", context_key="abc")},
    )
    raw = WordTranslationService._context_payload(
        analysis, element, previous_text="P" * 1000, next_text="N" * 1000, table_context=None
    )
    payload = json.loads(raw)
    assert len(payload["word_structure"]["previous_text"]) == 280
    assert len(payload["word_structure"]["next_text"]) == 280
    assert "full_element_text" not in payload
    assert len(raw) < 1200
