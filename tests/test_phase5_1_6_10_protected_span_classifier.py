import json

from translator.cache_manager import CacheManager
from translator.powerpoint_com.semantic_blocks import SemanticTextBlock
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine, TranslationRequest
from translator.translation.protection import ProtectedSpanEngine
from translator.translation_memory import TranslationMemory


PAGE37_BODY = "\r".join([
    "Dairy & Plant Based Product Types:",
    "Fermented Dairy or Plant Based Product (Original / Flavoured)",
    "Dairy or Plant Based Drinks ",
    "Non-Dairy / Plant Based Creamer",
    "Dairy or Plant Based Dessert",
    "Samples Selection Principle:",
    "List all the brands and SKUs produced in relevant plant(s).",
    "Select one top brand with the highest volume production (the most produced and most available to source)",
    "If there are several variants, choose the least flavoured one (original).",
    "If there are several packaging type, choose the most inert packaging material, when possible. ",
    "Choose SKU relevant to number of training participants for final sample selection (e.g., choose the the SKU with packaging volume of 1000ml for 20 trainees and 500ml for 10 trainees)",
    "Evaluate the overall profile of the chosen variant and ensure it represents the product category.",
])


class FailingRecoveryClient:
    def __init__(self):
        self.num_predict = 256
        self.calls = 0

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        self.calls += 1
        payload = json.loads(user)
        if payload.get("task") == "zero_untranslated_recovery_parts":
            return {"parts": []}
        return {"translation": "Terjemahan tanpa nilai terlindungi"}


def test_page37_sku_is_not_misclassified_as_chemical_formula():
    block = SemanticTextBlock.encode(PAGE37_BODY)
    protected = ProtectedSpanEngine().protect(block.encoded_text)
    values = list(protected.mapping.values())

    assert "SKU" not in values
    assert "SKUs" not in values
    assert "1000ml" in values
    assert "20" in values
    assert "500ml" in values
    assert "10" in values


def test_true_immutable_patterns_remain_protected():
    source = "Use CO2 and H2O; see QFS-AE-SPT-013; dose 250 mL at pH 6.5."
    protected = ProtectedSpanEngine().protect(source)
    values = set(protected.mapping.values())

    assert "CO2" in values
    assert "H2O" in values
    assert "QFS-AE-SPT-013" in values
    assert "250 mL" in values
    assert "pH" in values
    assert "6.5" in values


def test_manual_review_reports_recovery_failure_chain(tmp_path):
    client = FailingRecoveryClient()
    engine = TranslationEngine(
        client=client,
        model="primary",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase51610-test",
        terminology_version="test",
        batch_enabled=False,
        fallback_model="",
    )
    source = "Add 1000 ml water"
    result = engine.translate(
        source,
        context_key="diagnostic",
        semantic_role="body",
        full_element_text=source,
    )

    assert result.status == "manual_review"
    assert "recovery_line_primary" in result.error
    assert "Protected token hilang" in result.error
    assert "Recovery response" in result.error or "Recovery part" in result.error
