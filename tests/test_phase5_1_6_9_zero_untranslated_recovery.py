
import json

from translator.cache_manager import CacheManager
from translator.powerpoint_com.semantic_blocks import SemanticTextBlock
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine, TranslationRequest
from translator.translation_memory import TranslationMemory


class RecoveryClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.num_predict = 256

    def chat_structured(self, *, model, system, user, schema, num_predict_override=None):
        payload = json.loads(user)
        self.calls.append({
            "model": model,
            "payload": payload,
            "schema": schema,
            "num_predict_override": num_predict_override,
        })
        if not self.responses:
            raise AssertionError("Unexpected extra Ollama call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def make_engine(tmp_path, client, *, fallback_model=""):
    return TranslationEngine(
        client=client,
        model="primary",
        fallback_model=fallback_model,
        fallback_enabled=bool(fallback_model),
        translation_memory=TranslationMemory(tmp_path / "tm.db"),
        cache=CacheManager(tmp_path / "cache.db"),
        terminology=TerminologyLock([]),
        domain="food_science",
        prompt_version="phase5169-test",
        terminology_version="test",
        batch_enabled=False,
    )


def test_multiline_count_mismatch_recovers_per_visual_line(tmp_path):
    block = SemanticTextBlock.encode("Training Room\vRequirement")
    client = RecoveryClient([
        {"lines": ["Persyaratan Ruang Pelatihan"]},
        {"lines": ["Persyaratan Ruang Pelatihan"]},
        {"parts": [{"id": "part_0001", "translation": "Ruang Pelatihan"}]},
        {"parts": [{"id": "part_0001", "translation": "Persyaratan"}]},
    ])
    engine = make_engine(tmp_path, client)
    req = TranslationRequest(
        text=block.encoded_text,
        context_key="title",
        semantic_role="slide_title",
        full_element_text=block.flattened_text,
        line_segments=block.line_segments,
        break_tokens=block.break_tokens,
    )

    result = engine.translate_many([req])[0]

    assert result.status == "translated"
    assert result.origin == "recovery_line_primary"
    assert block.decode(result.target_text) == "Ruang Pelatihan\vPersyaratan"
    assert engine.stats["recovery_attempts"] == 1
    assert engine.stats["recovery_success"] == 1
    assert engine.stats["manual_review"] == 0
    assert [call["payload"]["task"] for call in client.calls[-2:]] == [
        "zero_untranslated_recovery_parts",
        "zero_untranslated_recovery_parts",
    ]


def test_protected_token_loss_recovers_by_reconstructing_token_in_code(tmp_path):
    source = "Add 1000 ml water"
    client = RecoveryClient([
        {"translation": "Tambahkan air"},
        {"translation": "Tambahkan air"},
        {
            "parts": [
                {"id": "part_0001", "translation": "Tambahkan"},
                {"id": "part_0002", "translation": "air"},
            ]
        },
    ])
    engine = make_engine(tmp_path, client)

    result = engine.translate(
        source,
        context_key="water-preparation",
        semantic_role="body",
        full_element_text=source,
    )

    assert result.status == "translated"
    assert result.origin == "recovery_line_primary"
    assert result.target_text == "Tambahkan 1000 ml air"
    assert engine.stats["recovery_success"] == 1
    recovery_payload = client.calls[-1]["payload"]
    assert recovery_payload["task"] == "zero_untranslated_recovery_parts"
    assert "1000 ml" not in " ".join(row["source"] for row in recovery_payload["parts"])


def test_recovery_uses_fallback_model_after_primary_recovery_fails(tmp_path):
    block = SemanticTextBlock.encode("Short\vBreak")
    client = RecoveryClient([
        {"lines": ["Istirahat"]},                 # primary whole element
        {"lines": ["Istirahat"]},                 # mandatory retry
        {"lines": ["Istirahat"]},                 # fallback whole element
        {"parts": []},                            # primary line recovery fails
        {"parts": [{"id": "part_0001", "translation": "Istirahat"}]},
        {"parts": [{"id": "part_0001", "translation": "Singkat"}]},
    ])
    engine = make_engine(tmp_path, client, fallback_model="strong")
    req = TranslationRequest(
        text=block.encoded_text,
        context_key="break-title",
        semantic_role="slide_title",
        full_element_text=block.flattened_text,
        line_segments=block.line_segments,
        break_tokens=block.break_tokens,
    )

    result = engine.translate_many([req])[0]

    assert result.status == "translated"
    assert result.origin == "recovery_line_fallback"
    assert block.decode(result.target_text) == "Istirahat\vSingkat"
    assert engine.stats["recovery_success"] == 1
    assert engine.stats["unresolved_after_recovery"] == 0
    assert client.calls[-1]["model"] == "strong"


def test_manual_review_only_after_recovery_pipeline_exhausted(tmp_path):
    block = SemanticTextBlock.encode("Training Room\vRequirement")
    client = RecoveryClient([
        {"lines": ["Ruang Pelatihan"]},
        {"lines": ["Ruang Pelatihan"]},
        {"parts": []},
    ])
    engine = make_engine(tmp_path, client)
    req = TranslationRequest(
        text=block.encoded_text,
        context_key="title",
        semantic_role="slide_title",
        full_element_text=block.flattened_text,
        line_segments=block.line_segments,
        break_tokens=block.break_tokens,
    )

    result = engine.translate_many([req])[0]

    assert result.status == "manual_review"
    assert engine.stats["recovery_attempts"] == 1
    assert engine.stats["recovery_failures"] == 1
    assert engine.stats["unresolved_after_recovery"] == 1
    assert engine.stats["manual_review"] == 1



def test_multiword_no_change_is_recovered_instead_of_silently_skipped(tmp_path):
    source = "According to Product Categories Required"
    client = RecoveryClient([
        {"translation": source},
        {"translation": source},
        {"parts": [{"id": "part_0001", "translation": "Sesuai Kategori Produk yang Diperlukan"}]},
    ])
    engine = make_engine(tmp_path, client)

    result = engine.translate(
        source,
        context_key="agenda-subtitle",
        semantic_role="slide_title",
        full_element_text=source,
    )

    assert result.status == "translated"
    assert result.origin == "recovery_line_primary"
    assert result.target_text == "Sesuai Kategori Produk yang Diperlukan"
    assert engine.stats["manual_review"] == 0
