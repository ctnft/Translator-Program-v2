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


def test_repeated_title_is_translated_while_repeated_corner_brand_is_preserved():
    stats = PresentationStats(
        presentation_name="training.pptx",
        slide_count=6,
        slide_width=1000,
        slide_height=600,
    )
    repeated_title = (
        "Agenda Building and Sessions Customization\v"
        "According to Product Categories Required"
    )
    elements = []
    for slide in range(1, 7):
        # Large recurring top-center content: must remain a slide title and translate.
        elements.append(
            element(slide, 1, repeated_title, top=45, left=120, width=760, height=90, font=30)
        )
        elements.append(
            element(slide, 2, f"Session content {slide}", top=190, left=120, width=700, font=17)
        )
        # Small repeated peripheral identity: preserve.
        elements.append(
            element(
                slide,
                3,
                "Global Sensory Solutions",
                top=555,
                left=820,
                width=150,
                height=18,
                font=9,
            )
        )

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)

    title = analysis.elements["slide3:shape1:text_shape"]
    assert title.semantic_role == "slide_title"
    assert title.translate_policy == "translate"
    assert repeated_title.replace("\v", " ") not in analysis.profile.preserve_phrases

    brand = analysis.elements["slide3:shape3:text_shape"]
    assert brand.semantic_role == "persistent_branding"
    assert brand.translate_policy == "preserve"
    assert "Global Sensory Solutions" in analysis.profile.preserve_phrases


def test_repeated_top_center_title_case_phrase_is_not_auto_preserved_even_without_manual_terms():
    stats = PresentationStats(
        presentation_name="deck.pptx",
        slide_count=5,
        slide_width=1000,
        slide_height=600,
    )
    elements = []
    for slide in range(1, 6):
        elements.append(
            element(slide, 1, "Product Categories Required", top=50, left=180, width=640, font=32)
        )
        elements.append(
            element(slide, 2, f"Different body {slide}", top=220, left=180, width=640, font=16)
        )

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)
    info = analysis.elements["slide2:shape1:text_shape"]
    assert info.semantic_role == "slide_title"
    assert info.translate_policy == "translate"
    assert "Product Categories Required" not in analysis.profile.preserve_phrases
