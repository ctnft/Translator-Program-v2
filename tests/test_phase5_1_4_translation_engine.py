import json

from translator.cache_manager import CacheManager
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.last_user = None

    def chat_structured(self, *, model, system, user, schema):
        self.calls += 1
        self.last_user = json.loads(user)
        source = self.last_user["source_text"]
        if "__TERM_0001__" in source and "__PROTECTED_0001__" in source:
            translation = "__TERM_0001__ diukur pada __PROTECTED_0001__"
        else:
            translation = "Terjemahan teknis"
        return {"translation": translation, "should_translate": True, "notes": ""}


def make_engine(tmp_path, client=None):
    client = client or FakeClient()
    terms = [
        {"source": "water activity", "target": "aktivitas air", "status": "locked"},
        {"source": "shelf life", "target": "umur simpan", "status": "locked"},
    ]
    return TranslationEngine(
        client=client,
        model="fake-model",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock(terms),
        domain="food_science",
        terminology_version="test-v1",
    ), client


def test_exact_locked_term_skips_ollama(tmp_path):
    engine, client = make_engine(tmp_path)
    result = engine.translate("Water Activity")
    assert result.target_text == "aktivitas air"
    assert result.origin == "locked"
    assert client.calls == 0


def test_locked_term_and_number_are_restored(tmp_path):
    engine, client = make_engine(tmp_path)
    result = engine.translate("Water activity is measured at 25 °C")
    assert result.status == "translated"
    assert result.target_text == "aktivitas air diukur pada 25 °C"
    assert client.calls == 1
    assert "__TERM_0001__" in client.last_user["source_text"]
    assert "__PROTECTED_0001__" in client.last_user["source_text"]


def test_translation_memory_prevents_second_ollama_call(tmp_path):
    engine, client = make_engine(tmp_path)
    first = engine.translate("Sensory evaluation")
    second = engine.translate("Sensory evaluation")
    assert first.target_text == "Terjemahan teknis"
    assert second.target_text == "Terjemahan teknis"
    assert second.origin == "translation_memory"
    assert client.calls == 1
