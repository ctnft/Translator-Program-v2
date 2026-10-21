import json

import pytest

from translator.cache_manager import CacheManager
from translator.terminology_lock import LockedText, TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation.protection import ProtectedSpanEngine, ProtectedText
from translator.translation_memory import TranslationMemory
from translator.yaml_loader import TerminologyLoader


class RetryClient:
    def __init__(self, responses, num_predict=256):
        self.responses = list(responses)
        self.calls = []
        self.num_predict = num_predict

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        self.calls.append({
            "model": model,
            "system": system,
            "user": json.loads(user),
            "num_predict_override": num_predict_override,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_engine(tmp_path, client, terminology=None, fallback_model=""):
    return TranslationEngine(
        client=client,
        model="primary",
        fallback_model=fallback_model,
        fallback_enabled=bool(fallback_model),
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock(terminology or []),
        domain="food_science",
        prompt_version="phase5164-test",
        terminology_version="1.4-test",
        batch_enabled=False,
    )


def test_protected_restore_accepts_literal_when_model_reintroduces_original():
    protected = ProtectedText("__PROTECTED_0001__", {"__PROTECTED_0001__": "CO2"})
    assert protected.restore("CO2") == "CO2"


def test_protected_restore_still_rejects_truly_missing_literal():
    protected = ProtectedText("__PROTECTED_0001__", {"__PROTECTED_0001__": "CO2"})
    with pytest.raises(ValueError, match="Protected token hilang"):
        protected.restore("karbon dioksida")


def test_locked_restore_accepts_literal_target_when_model_reintroduces_it():
    locked = LockedText("__TERM_0001__", {"__TERM_0001__": "GMP Flavour Standard"})
    assert locked.restore("GMP Flavour Standard") == "GMP Flavour Standard"


def test_engine_retries_recoverable_structured_failure(tmp_path):
    client = RetryClient([
        ValueError("Unterminated string"),
        {"translation": "Teks instruksi yang lengkap"},
    ])
    engine = make_engine(tmp_path, client)

    result = engine.translate(
        "A long instructional sentence that must be translated completely.",
        semantic_role="body",
        context_key="slide28-body",
        full_element_text="A long instructional sentence that must be translated completely.",
    )

    assert result.status == "translated"
    assert result.target_text == "Teks instruksi yang lengkap"
    assert len(client.calls) == 2
    assert engine.stats["ollama_forced_retry"] == 1


def test_long_single_request_gets_larger_num_predict_budget(tmp_path):
    source = "Instruction " * 180
    client = RetryClient([{"translation": "Instruksi lengkap"}], num_predict=256)
    engine = make_engine(tmp_path, client)

    result = engine.translate(
        source,
        semantic_role="body",
        context_key="long-body",
        full_element_text=source,
    )

    assert result.status == "translated"
    assert client.calls[0]["num_predict_override"] > 256


def test_tm_machine_results_are_isolated_by_engine_memory_version(tmp_path):
    tm = TranslationMemory(tmp_path / "tm.db")
    tm.save(
        "Medicinal",
        "Pedas",
        domain="food_science",
        context_hash="ctx",
        memory_version="old-policy",
    )
    client = RetryClient([{"translation": "Medisinal"}])
    engine = TranslationEngine(
        client=client,
        model="primary",
        translation_memory=tm,
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5164-test",
        terminology_version="1.4-test",
        batch_enabled=False,
    )

    result = engine.translate("Medicinal", context_key="ctx", semantic_role="table_cell")

    assert result.target_text == "Medisinal"
    assert result.origin != "translation_memory"
    assert len(client.calls) == 1


def test_phase5164_terminology_contains_reviewed_food_science_terms():
    from pathlib import Path
    terminology_path = Path(__file__).resolve().parents[1] / "terminology.yaml"
    data = TerminologyLoader().load(terminology_path)
    locked = {
        item["source"].casefold(): item.get("target")
        for item in data["terms"]
        if item.get("status") == "locked"
    }
    assert locked["origin of off notes"] == "Sumber Rasa yang Menyimpang"
    assert locked["safety precautions"] == "Tindakan Pencegahan Keselamatan"
    assert locked["still water"] == "Air Tanpa Karbonasi"
    assert locked["sparkling water"] == "Air Berkarbonasi"
    assert locked["flavoured beverages"] == "Minuman Berperisa"


def test_break_marker_loss_is_retried_inside_engine(tmp_path):
    client = RetryClient([
        {"translation": "Induksi Keselamatan"},
        {"translation": "Induksi __PPT_BREAK_0001__ Keselamatan"},
    ])
    engine = make_engine(tmp_path, client)

    result = engine.translate(
        "Safety __PPT_BREAK_0001__ Induction",
        semantic_role="slide_title",
        context_key="title",
        full_element_text="Safety Induction",
    )

    assert result.status == "translated"
    assert "__PPT_BREAK_0001__" in result.target_text
    assert len(client.calls) == 2
