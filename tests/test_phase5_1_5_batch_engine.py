import json

from translator.cache_manager import CacheManager
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory


class BatchClient:
    def __init__(self, *, omit_second=False):
        self.calls = []
        self.omit_second = omit_second

    def chat_structured(
        self,
        *,
        model,
        system,
        user,
        schema,
        num_predict_override=None,
    ):
        payload = json.loads(user)
        self.calls.append((payload["task"], num_predict_override, payload))
        if payload["task"] == "translate_batch":
            rows = []
            for index, segment in enumerate(payload["segments"], start=1):
                if self.omit_second and index == 2:
                    continue
                source = segment["source_text"]
                if source == "Opening":
                    target = "Pembukaan"
                elif source.startswith("Day "):
                    target = source.replace("Day ", "Hari ", 1)
                else:
                    target = f"ID {source}"
                rows.append({"id": segment["id"], "translation": target})
            return {"translations": rows}

        source = payload["source_text"]
        if source.startswith("Day "):
            target = source.replace("Day ", "Hari ", 1)
        elif source == "Opening":
            target = "Pembukaan"
        else:
            target = f"ID {source}"
        return {"translation": target}


def make_engine(tmp_path, client, **kwargs):
    return TranslationEngine(
        client=client,
        model="fake-model",
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase515-test",
        terminology_version="test-v1",
        batch_enabled=True,
        batch_size=8,
        batch_max_chars=6000,
        batch_num_predict=1024,
        **kwargs,
    )


def test_translate_many_deduplicates_and_batches(tmp_path):
    client = BatchClient()
    engine = make_engine(tmp_path, client)

    results = engine.translate_many([
        ("Opening", "slide context"),
        ("Opening", "slide context"),
        ("Day 1", "slide context"),
    ])

    assert [result.target_text for result in results] == [
        "Pembukaan",
        "Pembukaan",
        "Hari 1",
    ]
    assert len(client.calls) == 1
    assert client.calls[0][0] == "translate_batch"
    assert client.calls[0][1] == 1024
    assert len(client.calls[0][2]["segments"]) == 2
    assert engine.stats["deduplicated_segments"] == 1
    assert engine.stats["batch_calls"] == 1
    assert engine.stats["batch_segments"] == 2


def test_missing_batch_id_falls_back_only_for_missing_segment(tmp_path):
    client = BatchClient(omit_second=True)
    engine = make_engine(tmp_path, client)

    results = engine.translate_many([
        ("Opening", "ctx"),
        ("Day 1", "ctx"),
    ])

    assert results[0].target_text == "Pembukaan"
    assert results[1].target_text == "Hari 1"
    assert [call[0] for call in client.calls] == ["translate_batch", "translate_segment"]
    assert engine.stats["batch_fallback_single"] == 1


def test_batch_can_be_disabled_without_changing_results(tmp_path):
    client = BatchClient()
    engine = make_engine(tmp_path, client)
    engine.batch_enabled = False

    results = engine.translate_many([
        ("Opening", "ctx"),
        ("Day 1", "ctx"),
    ])

    assert [result.target_text for result in results] == ["Pembukaan", "Hari 1"]
    assert [call[0] for call in client.calls] == ["translate_segment", "translate_segment"]
    assert engine.stats["batch_calls"] == 0
