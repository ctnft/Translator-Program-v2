import json

from translator.cache_manager import CacheManager
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory


class LegacyFalseFlagClient:
    """Simulates a model that returns a valid translation but incorrectly says skip."""

    def __init__(self):
        self.calls = 0
        self.schemas = []

    def chat_structured(self, *, model, system, user, schema):
        self.calls += 1
        self.schemas.append(schema)
        source = json.loads(user)["source_text"]
        mapping = {
            "Opening": "Pembukaan",
            "Day 1": "Hari __PROTECTED_0001__" if "__PROTECTED_0001__" in source else "Hari 1",
        }
        translated = mapping.get(source, "Terjemahan")
        return {
            "translation": translated,
            "should_translate": False,  # legacy/advisory flag must NOT block write
        }


class FirstNoopThenTranslateClient:
    def __init__(self):
        self.calls = 0

    def chat_structured(self, *, model, system, user, schema):
        self.calls += 1
        if self.calls == 1:
            return {"translation": "Opening", "should_translate": False}
        return {"translation": "Pembukaan", "should_translate": False}


class AlwaysNoopClient:
    def __init__(self):
        self.calls = 0

    def chat_structured(self, *, model, system, user, schema):
        self.calls += 1
        return {"translation": "Danone", "should_translate": False}


def make_engine(tmp_path, client):
    return TranslationEngine(
        client=client,
        model="fake-model",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5145-test",
        terminology_version="test-v1",
    )


def test_legacy_should_translate_false_cannot_cancel_valid_translation(tmp_path):
    client = LegacyFalseFlagClient()
    engine = make_engine(tmp_path, client)

    result = engine.translate("Opening")

    assert result.status == "translated"
    assert result.target_text == "Pembukaan"
    assert result.origin == "ollama"
    assert engine.stats["llm_skip_overridden"] == 1
    assert client.calls == 1
    assert "should_translate" not in client.schemas[0]["required"]


def test_noop_gets_one_mandatory_retry(tmp_path):
    client = FirstNoopThenTranslateClient()
    engine = make_engine(tmp_path, client)

    result = engine.translate("Opening")

    assert result.status == "translated"
    assert result.target_text == "Pembukaan"
    assert client.calls == 2
    assert engine.stats["ollama_forced_retry"] == 1


def test_pure_noop_after_retry_is_not_saved_to_tm_or_cache(tmp_path):
    client = AlwaysNoopClient()
    engine = make_engine(tmp_path, client)

    first = engine.translate("Danone")
    second = engine.translate("Danone")

    assert first.status == "skipped"
    assert first.origin == "ollama_no_change"
    assert second.status == "skipped"
    assert client.calls == 4  # no TM/cache poisoning
