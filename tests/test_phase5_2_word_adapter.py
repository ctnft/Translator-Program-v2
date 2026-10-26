from pathlib import Path

import pytest

from translator.word_com.adapter import WordComAdapter
from translator.word_com.errors import UnsafeOutputPathError
from translator.word_com.intelligence import WordDocumentAnalyzer
from translator.word_com.models import WordDocumentStats, WordElement
from translator.word_com.translation_service import WordTranslationService, WORD_TRANSLATION_VERSION
from translator.word_com.walker import WordWalker, _trim_terminal_markers


def test_word_terminal_markers_are_not_part_of_translatable_text():
    assert _trim_terminal_markers("Hello\r") == ("Hello", 1)
    assert _trim_terminal_markers("Cell text\r\x07") == ("Cell text", 2)
    assert _trim_terminal_markers("Soft\vBreak") == ("Soft\vBreak", 0)


def test_word_element_keys_are_stable_and_surface_specific():
    paragraph = WordElement(kind="paragraph", text="Hello", paragraph_index=3, range_start=10, range_end=15)
    cell = WordElement(kind="table_cell", text="No", table_index=2, cell_index=4, row=1, column=1)
    assert WordWalker.element_key(paragraph) == "word:main:p3:range10-15"
    assert WordWalker.element_key(cell) == "word:main:table2:cell4:r1:c1"


def test_word_analyzer_preserves_fields_and_content_controls():
    elements = [
        WordElement(kind="paragraph", text="Page 1 of 10", paragraph_index=1, range_start=0, range_end=12, has_fields=True),
        WordElement(kind="paragraph", text="Controlled text", paragraph_index=2, range_start=20, range_end=35, has_content_controls=True),
    ]
    analysis = WordDocumentAnalyzer().analyze(WordDocumentStats(document_name="a.docx"), elements)
    first = analysis.elements[WordWalker.element_key(elements[0])]
    second = analysis.elements[WordWalker.element_key(elements[1])]
    assert first.translate_policy == "preserve"
    assert "contains_word_field" in first.reasons
    assert second.translate_policy == "preserve"
    assert "contains_content_control" in second.reasons


def test_word_analyzer_detects_explicit_brand_cue_and_protects_inline_brand():
    elements = [
        WordElement(kind="paragraph", text="Brands | Danone", paragraph_index=1, range_start=0, range_end=15),
        WordElement(kind="paragraph", text="Evaluate Danone samples", paragraph_index=2, range_start=20, range_end=43),
    ]
    analysis = WordDocumentAnalyzer().analyze(WordDocumentStats(document_name="a.docx"), elements)
    assert "Danone" in analysis.profile.brand_entities
    body = analysis.elements[WordWalker.element_key(elements[1])]
    assert "Danone" in body.protected_entities


def test_word_analyzer_detects_product_brand_column():
    elements = [
        WordElement(kind="table_cell", text="Product/Brand Name", table_index=1, cell_index=1, row=1, column=2),
        WordElement(kind="table_cell", text="Evian Sparkling", table_index=1, cell_index=2, row=2, column=2),
        WordElement(kind="table_cell", text="Still Water", table_index=1, cell_index=3, row=2, column=1),
    ]
    analysis = WordDocumentAnalyzer().analyze(WordDocumentStats(document_name="a.docx"), elements)
    assert "Evian Sparkling" in analysis.profile.brand_entities
    brand = analysis.elements[WordWalker.element_key(elements[1])]
    assert brand.translate_policy == "preserve"


def test_word_table_context_interprets_stop_as_finish():
    elements = [
        WordElement(kind="table_cell", text="Start", table_index=1, cell_index=1, row=1, column=1),
        WordElement(kind="table_cell", text="Stop", table_index=1, cell_index=2, row=1, column=2),
        WordElement(kind="table_cell", text="08.00", table_index=1, cell_index=3, row=2, column=1),
        WordElement(kind="table_cell", text="08.15", table_index=1, cell_index=4, row=2, column=2),
    ]
    contexts = WordTranslationService._table_contexts(elements)
    stop = contexts[WordWalker.element_key(elements[1])]
    assert stop["semantic_hint"] == "schedule_end_time_header"
    assert stop["preferred_translation"] == "Selesai"


def test_word_table_context_interprets_no_as_numbering_header():
    elements = [
        WordElement(kind="table_cell", text="No.", table_index=1, cell_index=1, row=1, column=1),
        WordElement(kind="table_cell", text="Item", table_index=1, cell_index=2, row=1, column=2),
        WordElement(kind="table_cell", text="1", table_index=1, cell_index=3, row=2, column=1),
        WordElement(kind="table_cell", text="2", table_index=1, cell_index=4, row=3, column=1),
    ]
    contexts = WordTranslationService._table_contexts(elements)
    no = contexts[WordWalker.element_key(elements[0])]
    assert no["semantic_hint"] == "sequence_number_header"
    assert no["preferred_translation"] == "No."


def test_word_checkpoint_version_is_isolated_from_powerpoint():
    assert WORD_TRANSLATION_VERSION == "phase522-word-performance-v1"


def test_word_adapter_rejects_non_docx_output(tmp_path):
    adapter = WordComAdapter()

    class FakeDoc:
        FullName = str(tmp_path / "source.docx")
        Path = str(tmp_path)

    Path(FakeDoc.FullName).write_bytes(b"fake")
    with pytest.raises(UnsafeOutputPathError):
        adapter.open_or_create_translation_copy(object(), FakeDoc(), tmp_path / "out.doc")
