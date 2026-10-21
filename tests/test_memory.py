from translator.translation_memory import TranslationMemory


def test_memory_lookup():

    memory = TranslationMemory(
        "test.db"
    )


    memory.save(
        source="water activity",
        target="aktivitas air"
    )


    result = memory.lookup(
        "water activity"
    )


    assert result == "aktivitas air"