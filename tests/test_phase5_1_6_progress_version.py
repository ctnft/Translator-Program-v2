from translator.progress import TranslationProgressStore


def test_progress_isolated_by_translation_version(tmp_path):
    store = TranslationProgressStore(tmp_path / "progress.db")
    store.save(
        "doc",
        "element",
        "Safety Induction",
        "Induksi Keamanan",
        "completed",
        "ollama",
        translation_version="phase515",
    )

    assert store.get(
        "doc", "element", "Safety Induction", translation_version="phase516-context-v1"
    ) is None
    old = store.get(
        "doc", "element", "Safety Induction", translation_version="phase515"
    )
    assert old["target_text"] == "Induksi Keamanan"
