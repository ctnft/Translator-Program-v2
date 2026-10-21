from pathlib import Path

from translator.cache_manager import CacheManager
from translator.config import AppConfig, PROJECT_ROOT
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory


class TranslatingClient:
    def __init__(self, *, should_translate=True, translation="Pembukaan"):
        self.should_translate = should_translate
        self.translation = translation
        self.calls = 0

    def chat_structured(self, *, model, system, user, schema):
        self.calls += 1
        return {
            "translation": self.translation,
            "should_translate": self.should_translate,
            "notes": "",
        }


def make_engine(tmp_path, client):
    return TranslationEngine(
        client=client,
        model="fake-model",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5144-test",
        terminology_version="test-v1",
    )


def test_should_translate_false_is_not_saved_as_machine_translation(tmp_path):
    client = TranslatingClient(should_translate=False, translation="Opening")
    engine = make_engine(tmp_path, client)

    first = engine.translate("Opening")
    second = engine.translate("Opening")

    assert first.status == "skipped"
    assert first.target_text == "Opening"
    assert second.status == "skipped"
    # It must call Ollama again: no-op results must not poison TM/cache.
    assert client.calls == 4


def test_stale_translation_memory_source_equals_target_is_ignored(tmp_path):
    client = TranslatingClient(should_translate=True, translation="Pembukaan")
    engine = make_engine(tmp_path, client)
    engine.tm.save(
        "Opening",
        "Opening",
        domain="food_science",
        source_language="en",
        target_language="id",
        quality_status="machine_validated",
    )

    result = engine.translate("Opening")

    assert result.target_text == "Pembukaan"
    assert result.origin == "ollama"
    assert engine.stats["stale_tm_ignored"] == 0  # Phase 5.1.6.4 isolates older TM versions before lookup
    assert client.calls == 1


def test_runtime_directories_default_to_project_input_output(monkeypatch, tmp_path):
    monkeypatch.delenv("INPUT_DIR", raising=False)
    monkeypatch.delenv("OUTPUT_DIR", raising=False)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")

    config = AppConfig.load(str(env_file))

    assert config.input_dir == (PROJECT_ROOT / "input").resolve()
    assert config.output_dir == (PROJECT_ROOT / "output").resolve()
    assert config.input_dir.is_dir()
    assert config.output_dir.is_dir()
