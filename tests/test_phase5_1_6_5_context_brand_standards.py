import json
from pathlib import Path

from translator.cache_manager import CacheManager
from translator.document_intelligence.analyzer import DocumentIntelligenceAnalyzer
from translator.powerpoint_com.models import PresentationStats, TextElement
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory
from translator.yaml_loader import TerminologyLoader


class FakeClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.num_predict = 256

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        self.calls.append({
            "model": model,
            "system": system,
            "user": json.loads(user),
            "num_predict_override": num_predict_override,
        })
        return dict(self.response)


def _el(slide, shape, text, *, top=100, left=100, width=600, height=40, font=18, kind="text_shape", row=None, column=None, path=None):
    return TextElement(
        slide_index=slide,
        shape_id=shape,
        shape_name=f"Shape {shape}",
        kind=kind,
        text=text,
        shape_path=path or (shape,),
        row=row,
        column=column,
        left=left,
        top=top,
        width=width,
        height=height,
        font_size=font,
    )


def test_brand_slide_detects_product_names_but_not_category_labels():
    stats = PresentationStats(slide_count=3, slide_width=1000, slide_height=600)
    elements = []
    for slide in range(1, 4):
        elements.append(_el(slide, 1, "Global Sensory Solutions", top=15, left=20, width=220, font=12))
    elements += [
        _el(1, 2, "Waters and Beverages – Choosing Samples Example", top=60, left=150, width=700, font=30),
        _el(1, 3, "Still Water:", top=180, left=120),
        _el(1, 4, "Evian 1L", top=220, left=120),
        _el(1, 5, "Sparkling Water:", top=180, left=420),
        _el(1, 6, "Evian Sparkling", top=220, left=420),
        _el(1, 7, "Mizone", top=260, left=120),
        _el(1, 8, "Brands | Danone", top=500, left=650, width=220, font=12),
        _el(2, 2, "Other Training Content", top=60, left=150, width=700, font=30),
        _el(3, 2, "Other Training Content 2", top=60, left=150, width=700, font=30),
    ]

    analysis = DocumentIntelligenceAnalyzer().analyze(stats, elements)

    assert "Evian 1L" in analysis.profile.brand_entities
    assert "Evian" in analysis.profile.brand_entities
    assert "Evian Sparkling" in analysis.profile.brand_entities
    assert "Mizone" in analysis.profile.brand_entities
    assert "Danone" in analysis.profile.brand_entities
    assert "Still Water" not in analysis.profile.brand_entities
    assert "Sparkling Water" not in analysis.profile.brand_entities

    by_text = {info.source_text: info for info in analysis.elements.values()}
    assert by_text["Evian Sparkling"].semantic_role == "brand_entity"
    assert by_text["Evian Sparkling"].translate_policy == "preserve"
    assert by_text["Still Water:"].translate_policy == "translate"


def test_brand_name_is_protected_inside_larger_textbox(tmp_path):
    client = FakeClient({"translation": "Sajikan __DOC_PRESERVE_0001__ pada suhu dingin."})
    engine = TranslationEngine(
        client=client,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5165-test",
        terminology_version="std-test",
        batch_enabled=False,
    )
    engine.configure_document_context(
        summary="food sensory training; brand_entities=Evian Sparkling",
        preserve_phrases=["Evian Sparkling"],
    )

    result = engine.translate(
        "Serve Evian Sparkling at chilled temperature.",
        context_key="ctx",
        semantic_role="body",
        full_element_text="Serve Evian Sparkling at chilled temperature.",
    )

    assert result.target_text == "Sajikan Evian Sparkling pada suhu dingin."
    sent = client.calls[0]["user"]["source_text"]
    assert "Evian Sparkling" not in sent
    assert "__DOC_PRESERVE_0001__" in sent


def test_standard_food_science_lexicon_and_custom_override_merge():
    root = Path(__file__).resolve().parents[1]
    loader = TerminologyLoader()
    standard = loader.load(root / "food_science_standards.yaml")
    custom = loader.load(root / "terminology.yaml")
    merged = loader.merge(standard, custom)
    terms = {row["source"].casefold(): row for row in merged["terms"]}

    assert terms["non-dairy creamer"]["target"] == "Krimer Nabati"
    assert terms["dairy drinks"]["target"] == "Minuman Susu"
    assert terms["dairy / plant based dessert"]["target"] == "Makanan Pencuci Mulut Berbasis Susu/Nabati"
    assert terms["dairy-based desserts"]["target"] == "Makanan Pencuci Mulut Berbahan Dasar Susu"
    assert terms["carbonated water-based flavoured drinks"]["target"] == "Minuman Berbasis Air Berperisa yang Berkarbonat"
    # Custom/project terminology has the last word when the same source exists.
    assert terms["sensory analysis"]["target"] == "Analisis Sensori"


def test_authoritative_glossary_is_sent_to_model(tmp_path):
    terms = [{
        "source": "Non-dairy Creamer",
        "target": "Krimer Nabati",
        "status": "locked",
        "authority": "SNI_BSN",
        "reference": "SNI 4444:2018",
    }]
    client = FakeClient({"translation": "__TERM_0001__"})
    engine = TranslationEngine(
        client=client,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock(terms),
        domain="food_science",
        prompt_version="phase5165-test",
        terminology_version="std-test",
        batch_enabled=False,
    )

    result = engine.translate(
        "Non-dairy Creamer",
        context_key="ctx",
        semantic_role="body",
        full_element_text="Non-dairy Creamer",
    )

    # Exact locked term resolves before model; use a sentence to exercise prompt guidance.
    assert result.target_text == "Krimer Nabati"

    client2 = FakeClient({"translation": "Gunakan __TERM_0001__ untuk formulasi."})
    engine2 = TranslationEngine(
        client=client2,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm2.db"),
        cache=CacheManager(tmp_path / "cache2.db"),
        terminology=TerminologyLock(terms),
        domain="food_science",
        prompt_version="phase5165-test",
        terminology_version="std-test",
        batch_enabled=False,
    )
    result2 = engine2.translate(
        "Use Non-dairy Creamer for formulation.",
        context_key="ctx2",
        semantic_role="body",
        full_element_text="Use Non-dairy Creamer for formulation.",
    )
    assert result2.target_text == "Gunakan Krimer Nabati untuk formulasi."
    guidance = client2.calls[0]["user"]["authoritative_terminology"]
    assert guidance[0]["target"] == "Krimer Nabati"
    assert guidance[0]["authority"] == "SNI_BSN"
    assert "BPOM/SNI" in client2.calls[0]["system"]
