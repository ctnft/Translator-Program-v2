import json

from translator.cache_manager import CacheManager
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine, TranslationRequest
from translator.translation_memory import TranslationMemory


class ContextClient:
    def __init__(self):
        self.calls = []

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        payload = json.loads(user)
        self.calls.append((model, payload))
        source = payload.get("source_text", "")
        if model == "strong-model":
            return {"translation": "Induksi Keselamatan"}
        if source == "Safety Induction":
            return {"translation": "Induksi Keamanan"}
        if source == "Panel":
            context = payload.get("slide_context", "")
            return {"translation": "Panel sensori" if "sensory" in context else "Panel kontrol"}
        return {"translation": f"ID {source}"}


def make_engine(tmp_path, client, **kwargs):
    return TranslationEngine(
        client=client,
        model="primary-model",
        fallback_model=kwargs.pop("fallback_model", ""),
        fallback_enabled=kwargs.pop("fallback_enabled", True),
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase516-test",
        terminology_version="test-v1",
        batch_enabled=False,
        **kwargs,
    )


def test_contextual_tm_does_not_reuse_different_context(tmp_path):
    client = ContextClient()
    engine = make_engine(tmp_path, client)

    first = engine.translate(
        "Panel",
        slide_context="sensory evaluation training",
        context_key="sensory-title",
        semantic_role="slide_title",
    )
    second = engine.translate(
        "Panel",
        slide_context="equipment control panel",
        context_key="equipment-title",
        semantic_role="slide_title",
    )

    assert first.target_text == "Panel sensori"
    # A second model call is required because the semantic context differs.
    assert len(client.calls) == 2
    assert second.origin != "translation_memory"


def test_document_preserve_skips_ollama(tmp_path):
    client = ContextClient()
    engine = make_engine(tmp_path, client)
    engine.configure_document_context(
        summary="training deck",
        preserve_phrases=["Global Sensory Solutions"],
    )

    result = engine.translate(
        "Global Sensory Solutions",
        context_key="branding",
        semantic_role="persistent_branding",
        preserve=True,
    )

    assert result.target_text == "Global Sensory Solutions"
    assert result.origin == "document_preserve"
    assert client.calls == []


def test_ambiguous_title_can_use_stronger_fallback(tmp_path):
    client = ContextClient()
    engine = make_engine(tmp_path, client, fallback_model="strong-model")

    result = engine.translate(
        "Safety Induction",
        slide_context=json.dumps(
            {
                "document": {"type": "training_material"},
                "slide": {"role": "training_protocol", "body": ["Emergency procedure"]},
            }
        ),
        context_key="training-title",
        semantic_role="slide_title",
        ambiguous=True,
    )

    assert result.target_text == "Induksi Keselamatan"
    assert result.origin == "fallback_model"
    assert [model for model, _ in client.calls] == ["primary-model", "strong-model"]
    assert engine.stats["fallback_success"] == 1


def test_preserve_locked_terminology_can_omit_target(tmp_path):
    client = ContextClient()
    engine = TranslationEngine(
        client=client,
        model="primary-model",
        translation_memory=TranslationMemory(tmp_path / "tm2.db"),
        cache=CacheManager(tmp_path / "cache2.db"),
        terminology=TerminologyLock([
            {"source": "Danone", "status": "preserve_locked"}
        ]),
        batch_enabled=False,
    )

    result = engine.translate("Danone")
    assert result.origin == "preserve_lock"
    assert result.target_text == "Danone"
    assert client.calls == []


class JointFragmentClient:
    def __init__(self):
        self.payload = None

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        payload = json.loads(user)
        self.payload = payload
        if payload["task"] == "translate_batch":
            rows = []
            for segment in payload["segments"]:
                # The model may redistribute meaning across fragments of one title.
                target = "Induksi" if segment["segment_index"] == 1 else "Keselamatan"
                rows.append({"id": segment["id"], "translation": target})
            return {"translations": rows}
        raise AssertionError("Expected batch")


def test_multiline_title_fragments_are_grouped_for_joint_translation(tmp_path):
    client = JointFragmentClient()
    engine = TranslationEngine(
        client=client,
        model="primary-model",
        translation_memory=TranslationMemory(tmp_path / "tm_joint.db"),
        cache=CacheManager(tmp_path / "cache_joint.db"),
        terminology=TerminologyLock([]),
        batch_enabled=True,
        batch_size=8,
        fallback_enabled=False,
    )
    requests = [
        TranslationRequest(
            text="Safety",
            semantic_role="slide_title",
            context_key="training-title",
            element_key="slide3:title",
            segment_index=1,
            segment_count=2,
            full_element_text="Safety / Induction",
        ),
        TranslationRequest(
            text="Induction",
            semantic_role="slide_title",
            context_key="training-title",
            element_key="slide3:title",
            segment_index=2,
            segment_count=2,
            full_element_text="Safety / Induction",
        ),
    ]

    results = engine.translate_many(requests)
    assert [r.target_text for r in results] == ["Induksi", "Keselamatan"]
    assert all(row["element_key"] == "slide3:title" for row in client.payload["segments"])
    assert [row["segment_index"] for row in client.payload["segments"]] == [1, 2]
