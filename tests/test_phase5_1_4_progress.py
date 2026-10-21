from translator.progress import TranslationProgressStore


def test_progress_roundtrip(tmp_path):
    store = TranslationProgressStore(tmp_path / "state.db")
    store.save("doc1", "slide1:shape1:text_shape", "Opening", "Pembukaan", "completed", "ollama")
    row = store.get("doc1", "slide1:shape1:text_shape", "Opening")
    assert row["target_text"] == "Pembukaan"
    assert row["status"] == "completed"
