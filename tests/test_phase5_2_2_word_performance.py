from pathlib import Path

from translator.config import AppConfig
from translator.progress import TranslationProgressStore
from translator.word_com.intelligence import WordDocumentAnalyzer
from translator.word_com.models import WordDocumentStats, WordElement
from translator.word_com.translation_service import WORD_TRANSLATION_VERSION, WordTranslationService
from translator.word_com.walker import WordWalker


def _analyze(texts):
    elements = [
        WordElement(kind="paragraph", text=text, paragraph_index=i, range_start=i * 100, range_end=i * 100 + len(text))
        for i, text in enumerate(texts, start=1)
    ]
    analysis = WordDocumentAnalyzer().analyze(
        WordDocumentStats(document_name="perf.docx"),
        elements,
        domain="civil_engineering_building",
        smart_eligibility=True,
    )
    return elements, analysis


def test_smart_filter_skips_nonlinguistic_numeric_units_and_identifier():
    elements, analysis = _analyze(["/", "123", "4×185 mm²", "C-0501B", "Key Outcomes"])
    policies = [analysis.elements[WordWalker.element_key(e)] for e in elements]
    assert policies[0].translate_policy == "preserve"
    assert "smart_skip_nonlinguistic" in policies[0].reasons
    assert policies[1].translate_policy == "preserve"
    assert policies[2].translate_policy == "preserve"
    assert "smart_skip_value_unit" in policies[2].reasons
    assert policies[3].translate_policy == "preserve"
    assert "smart_skip_identifier" in policies[3].reasons
    assert policies[4].translate_policy == "translate"


def test_smart_filter_skips_confident_indonesian_but_not_mixed_english():
    elements, analysis = _analyze([
        "Pekerjaan pembangunan harus dilaksanakan sesuai dokumen teknis yang disetujui.",
        "Dokumen technical proposal harus submitted sesuai persyaratan proyek.",
        "Structural System",
    ])
    first = analysis.elements[WordWalker.element_key(elements[0])]
    second = analysis.elements[WordWalker.element_key(elements[1])]
    third = analysis.elements[WordWalker.element_key(elements[2])]
    assert first.translate_policy == "preserve"
    assert "smart_skip_already_indonesian" in first.reasons
    assert second.translate_policy == "translate"
    assert third.translate_policy == "translate"


def test_smart_filter_can_be_disabled():
    element = WordElement(kind="paragraph", text="123", paragraph_index=1, range_start=0, range_end=3)
    analysis = WordDocumentAnalyzer().analyze(
        WordDocumentStats(document_name="a.docx"), [element], smart_eligibility=False
    )
    assert analysis.elements[WordWalker.element_key(element)].translate_policy == "translate"


def test_progress_save_many_is_atomic_and_versioned(tmp_path):
    store = TranslationProgressStore(tmp_path / "progress.db")
    records = [
        {
            "document_id": "doc",
            "element_key": "e1",
            "source_text": "Hello",
            "target_text": "Halo",
            "status": "pending_save",
            "origin": "ollama",
            "translation_version": WORD_TRANSLATION_VERSION,
        },
        {
            "document_id": "doc",
            "element_key": "e2",
            "source_text": "World",
            "target_text": "Dunia",
            "status": "pending_save",
            "origin": "ollama",
            "translation_version": WORD_TRANSLATION_VERSION,
        },
    ]
    store.save_many(records)
    assert store.get("doc", "e1", "Hello", WORD_TRANSLATION_VERSION)["status"] == "pending_save"
    assert store.get("doc", "e2", "World", WORD_TRANSLATION_VERSION)["target_text"] == "Dunia"
    for record in records:
        record["status"] = "completed"
    store.save_many(records)
    assert store.get("doc", "e1", "Hello", WORD_TRANSLATION_VERSION)["status"] == "completed"


def test_phase522_word_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("WORD_STATE_DB", raising=False)
    monkeypatch.delenv("WORD_SAVE_BATCH_SIZE", raising=False)
    monkeypatch.delenv("WORD_SMART_ELIGIBILITY", raising=False)
    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    config = AppConfig.load(str(env_file))
    assert config.word_state_db.name == "phase522-word.db"
    assert config.word_save_batch_size == 20
    assert config.word_smart_eligibility is True
    assert WORD_TRANSLATION_VERSION == "phase522-word-performance-v1"


def test_word_service_accepts_save_batch_and_smart_filter(tmp_path):
    class Dummy:
        pass
    service = WordTranslationService(
        engine=Dummy(),
        progress=TranslationProgressStore(tmp_path / "p.db"),
        save_batch_size=25,
        smart_eligibility=False,
    )
    assert service.save_batch_size == 25
    assert service.smart_eligibility is False


def test_word_analysis_uses_selected_domain_and_style():
    element = WordElement(kind="paragraph", text="Key Outcomes", paragraph_index=1, range_start=0, range_end=12)
    analysis = WordDocumentAnalyzer().analyze(
        WordDocumentStats(document_name="civil.docx"), [element],
        domain="civil_engineering_building", style="Civil engineer translation style", smart_eligibility=True
    )
    assert analysis.profile.subject == "civil_engineering_building"
    assert analysis.profile.style == "Civil engineer translation style"


def test_word_service_batches_document_save_calls(tmp_path):
    from translator.translation.engine import TranslationResult
    from translator.word_com.models import WordIntegrityResult

    elements = [
        WordElement(
            kind="paragraph",
            text=f"Translate this technical sentence number {i}",
            paragraph_index=i,
            range_start=i * 100,
            range_end=i * 100 + 40,
            style_name="Normal",
            outline_level=10,
        )
        for i in range(1, 26)
    ]
    stats = WordDocumentStats(document_name="batch.docx", page_count=2, paragraph_count=25, text_element_count=25)
    source_path = tmp_path / "batch.docx"
    source_path.write_bytes(b"fake-docx-for-unit-test")

    class FakeDoc:
        TrackRevisions = False
        def __init__(self, mapping=None):
            self.mapping = dict(mapping or {})

    source_doc = FakeDoc({WordWalker.element_key(e): e.text for e in elements})
    target_doc = FakeDoc(source_doc.mapping)

    class FakeAdapter:
        def __init__(self):
            self.save_calls = 0
        def attach_application(self): return object()
        def get_document(self, app, source_path_arg=None): return source_doc
        def ensure_saved_source(self, document): return source_path
        def open_or_create_translation_copy(self, app, document, output_path, resume=False):
            return target_doc, Path(output_path)
        def save(self, document): self.save_calls += 1
        def activate_document_window(self, document): pass

    class FakeWalker:
        inspect = lambda self, doc: (stats, elements)
        structure_snapshot = lambda self, doc: {"stable": True}
        compare_structure = lambda self, a, b: WordIntegrityResult(True, [])
        @staticmethod
        def element_key(element): return WordWalker.element_key(element)
        def read_element_text(self, doc, element): return doc.mapping[WordWalker.element_key(element)]
        def replace_text(self, doc, element, target):
            key = WordWalker.element_key(element)
            doc.mapping[key] = target
            return {
                "text": target,
                "style_before": "Normal",
                "style_after": "Normal",
                "font_style_sequence_before": [],
                "font_style_sequence_after": [],
            }

    class FakeEngine:
        model = "fake"
        fallback_model = ""
        domain = "civil_engineering_building"
        expert_profile = None
        recovery_enabled = True
        stats = {"batch_calls": 4, "ollama_single_calls": 0}
        def configure_document_context(self, **kwargs): pass
        def translate_many(self, requests):
            return [
                TranslationResult(r.text, "ID " + r.text, "fake_batch", status="translated")
                for r in requests
            ]

    adapter = FakeAdapter()
    progress = TranslationProgressStore(tmp_path / "state.db")
    service = WordTranslationService(
        engine=FakeEngine(), progress=progress, output_dir=tmp_path,
        adapter=adapter, walker=FakeWalker(), save_batch_size=10, smart_eligibility=False,
    )
    report = service.translate(
        source_path=str(source_path), output_path=str(tmp_path / "out.docx"), apply=True
    )
    assert report["written_this_run"] == 25
    assert report["word_performance"]["word_save_calls"] == 3
    assert adapter.save_calls == 3
    for element in elements:
        key = WordWalker.element_key(element)
        row = progress.get(report["document_id"], key, element.text, WORD_TRANSLATION_VERSION)
        assert row["status"] == "completed"
