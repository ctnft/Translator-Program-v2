import pytest

from translator.powerpoint_com.semantic_blocks import SemanticTextBlock
from translator.powerpoint_com.translation_service import build_replacement_pairs


def test_multiline_title_is_one_semantic_block_and_preserves_break():
    block = SemanticTextBlock.encode("Safety\vInduction")

    assert block.flattened_text == "Safety Induction"
    assert block.break_count == 1
    assert "__PPT_BREAK_0001__" in block.encoded_text

    target = block.decode("Induksi __PPT_BREAK_0001__ Keselamatan")
    assert target == "Induksi\vKeselamatan"
    assert build_replacement_pairs("Safety\vInduction", target) == [
        ("Safety", "Induksi"),
        ("Induction", "Keselamatan"),
    ]


def test_multiple_mixed_powerpoint_breaks_are_restored_exactly():
    source = "Title\vLine 2\rLine 3\nLine 4"
    block = SemanticTextBlock.encode(source)
    translated = (
        "Judul __PPT_BREAK_0001__ Baris 2 "
        "__PPT_BREAK_0002__ Baris 3 __PPT_BREAK_0003__ Baris 4"
    )
    assert block.decode(translated) == "Judul\vBaris 2\rBaris 3\nBaris 4"


def test_missing_break_marker_is_rejected_instead_of_flattening_format():
    block = SemanticTextBlock.encode("Safety\vInduction")
    with pytest.raises(ValueError, match="harus muncul tepat sekali"):
        block.decode("Induksi Keselamatan")


def test_duplicate_break_marker_is_rejected():
    block = SemanticTextBlock.encode("Safety\vInduction")
    with pytest.raises(ValueError, match="tepat sekali"):
        block.decode(
            "Induksi __PPT_BREAK_0001__ Keselamatan __PPT_BREAK_0001__"
        )
