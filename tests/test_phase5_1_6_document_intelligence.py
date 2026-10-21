from translator.document_intelligence.analyzer import DocumentIntelligenceAnalyzer
from translator.powerpoint_com.models import PresentationStats, TextElement


def element(slide, path, text, *, top, left, width=700, height=60, font=28, kind="text_shape"):
    return TextElement(
        slide_index=slide,
        shape_id=path,
        shape_name=f"shape-{path}",
        kind=kind,
        text=text,
        shape_path=(path,),
        left=left,
        top=top,
        width=width,
        height=height,
        font_size=font,
    )


def build_deck():
    elements = []
    titles = [
        "Danone Trainer Training",
        "Greetings by Organizer",
        "Safety Induction",
        "Housekeeping Rules",
        "Training Agenda",
    ]
    bodies = [
        "Sensory training program",
        "Welcome and introduction",
        "Emergency procedure and safe behavior",
        "Be engaged\rBe on time\rNo cell phones on table",
        "Modules, objectives, and expectations",
    ]
    for slide, (title, body) in enumerate(zip(titles, bodies), start=1):
        elements.append(element(slide, 1, title, top=55, left=100, font=32))
        elements.append(element(slide, 2, body, top=190, left=100, font=16))
        elements.append(
            element(
                slide,
                3,
                "Global Sensory Solutions",
                top=545,
                left=820,
                width=150,
                height=20,
                font=10,
            )
        )
    return elements


def test_full_deck_analysis_detects_brand_titles_neighbors_and_profile():
    stats = PresentationStats(
        presentation_name="training.pptx",
        slide_count=5,
        slide_width=1000,
        slide_height=600,
    )
    analysis = DocumentIntelligenceAnalyzer().analyze(stats, build_deck())

    assert analysis.profile.document_type == "training_material"
    assert analysis.profile.subject == "food_sensory_science"
    assert "Global Sensory Solutions" in analysis.profile.preserve_phrases

    brand = analysis.elements["slide3:shape3:text_shape"]
    assert brand.semantic_role == "persistent_branding"
    assert brand.translate_policy == "preserve"
    assert brand.repetition_count == 5
    assert brand.position_bucket == "bottom_right"

    safety = analysis.elements["slide3:shape1:text_shape"]
    assert safety.semantic_role == "slide_title"
    assert safety.ambiguous is True
    assert analysis.slides[3].slide_role == "training_protocol"
    assert analysis.slides[3].previous_title == "Greetings by Organizer"
    assert analysis.slides[3].next_title == "Housekeeping Rules"

    housekeeping = analysis.elements["slide4:shape1:text_shape"]
    assert housekeeping.semantic_role == "slide_title"
    assert analysis.slides[4].body_text[0].startswith("Be engaged")


def test_context_key_is_stable_for_same_semantic_context():
    stats = PresentationStats(
        presentation_name="training.pptx",
        slide_count=5,
        slide_width=1000,
        slide_height=600,
    )
    analysis = DocumentIntelligenceAnalyzer().analyze(stats, build_deck())
    a = analysis.elements["slide3:shape1:text_shape"].context_key
    b = analysis.elements["slide4:shape1:text_shape"].context_key
    assert a == b  # both are slide_title + training_protocol within same document profile


def test_repeated_common_label_is_footer_not_brand_preserve():
    stats = PresentationStats(
        presentation_name="deck.pptx",
        slide_count=4,
        slide_width=1000,
        slide_height=600,
    )
    elements = []
    for slide in range(1, 5):
        elements.append(element(slide, 1, f"Topic {slide}", top=60, left=100, font=30))
        elements.append(
            element(slide, 2, "Confidential", top=560, left=430, width=140, height=20, font=9)
        )
    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)
    footer = analysis.elements["slide2:shape2:text_shape"]
    assert footer.semantic_role == "footer"
    assert footer.translate_policy == "translate"
    assert "Confidential" not in analysis.profile.preserve_phrases
