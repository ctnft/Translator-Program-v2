from translator.document_intelligence.analyzer import DocumentIntelligenceAnalyzer
from translator.powerpoint_com.models import PresentationStats, TextElement


def element(slide, path, text, *, top, left, width=700, height=60, font=28):
    return TextElement(
        slide_index=slide,
        shape_id=path,
        shape_name=f"shape-{path}",
        kind="text_shape",
        text=text,
        shape_path=(path,),
        left=left,
        top=top,
        width=width,
        height=height,
        font_size=font,
    )


def test_brand_is_preserved_even_if_one_slide_detects_same_phrase_as_title():
    """Regression for the real 385-slide deck.

    A persistent brand/header must not lose preserve status merely because one
    sparse slide causes the same phrase to become that slide's detected title.
    """
    stats = PresentationStats(
        presentation_name="training.pptx",
        slide_count=385,
        slide_width=1583,
        slide_height=890.5,
    )
    elements = []
    for slide in range(1, 386):
        # Stable top-left identity on essentially the whole deck.
        elements.append(
            element(
                slide,
                1,
                "Global Sensory Solutions",
                top=18,
                left=22,
                width=260,
                height=24,
                font=10,
            )
        )
        # One sparse brand slide intentionally has no other title/content. This
        # reproduces the real case where the repeated brand itself is selected
        # as the slide title once.
        if slide != 179:
            elements.append(
                element(
                    slide,
                    2,
                    f"Training Topic {slide}",
                    top=75,
                    left=260,
                    width=1000,
                    height=80,
                    font=30,
                )
            )

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)

    assert "Global Sensory Solutions" in analysis.profile.preserve_phrases
    header = analysis.elements["slide1:shape1:text_shape"]
    sparse_slide = analysis.elements["slide179:shape1:text_shape"]
    assert header.semantic_role == "persistent_branding"
    assert header.translate_policy == "preserve"
    # Preserve applies to the phrase consistently, including the dedicated
    # brand slide; a company identity must not be translated there either.
    assert sparse_slide.semantic_role == "persistent_branding"
    assert sparse_slide.translate_policy == "preserve"


def test_repeated_actual_title_remains_translatable_even_in_top_left_layout():
    stats = PresentationStats(
        presentation_name="agenda.pptx",
        slide_count=10,
        slide_width=1000,
        slide_height=600,
    )
    elements = []
    for slide in range(1, 11):
        elements.append(
            element(
                slide,
                1,
                "Operational Training Agenda",
                top=45,
                left=40,
                width=650,
                height=70,
                font=32,
            )
        )
        elements.append(
            element(slide, 2, f"Different session content {slide}", top=210, left=120, font=16)
        )

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)
    title = analysis.elements["slide5:shape1:text_shape"]
    assert title.semantic_role == "slide_title"
    assert title.translate_policy == "translate"
    assert "Operational Training Agenda" not in analysis.profile.preserve_phrases


def test_strong_all_caps_brand_can_be_preserved_in_large_deck_section():
    """A stable URL/all-caps brand may occur in only one section of a huge deck."""
    stats = PresentationStats(
        presentation_name="training.pptx",
        slide_count=385,
        slide_width=1583,
        slide_height=890.5,
    )
    elements = []
    for slide in range(1, 386):
        elements.append(
            element(
                slide,
                1,
                f"Topic {slide}",
                top=70,
                left=260,
                width=900,
                height=70,
                font=30,
            )
        )
        if slide <= 47:
            elements.append(
                element(
                    slide,
                    2,
                    "FLAVORACTI V. COM",
                    top=835,
                    left=1320,
                    width=220,
                    height=22,
                    font=9,
                )
            )

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)
    brand = analysis.elements["slide20:shape2:text_shape"]
    assert brand.semantic_role == "persistent_branding"
    assert brand.translate_policy == "preserve"
    assert "FLAVORACTI V. COM" in analysis.profile.preserve_phrases
