from translator.config import AppConfig


def test_ollama_performance_defaults(monkeypatch, tmp_path):
    names = [
        "OLLAMA_NUM_CTX",
        "OLLAMA_NUM_PREDICT",
        "OLLAMA_KEEP_ALIVE",
        "OLLAMA_THINK",
        "OLLAMA_TEMPERATURE",
        "OLLAMA_TIMEOUT_SECONDS",
        "OLLAMA_RETRIES",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    config = AppConfig.load(str(env_file))

    assert config.ollama_num_ctx == 4096
    assert config.ollama_num_predict == 256
    assert config.ollama_keep_alive == "30m"
    assert config.ollama_think is False
    assert config.ollama_temperature == 0
    assert config.ollama_timeout_seconds == 300
    assert config.ollama_retries == 1


def test_ollama_performance_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "8192")
    monkeypatch.setenv("OLLAMA_NUM_PREDICT", "128")
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "15m")
    monkeypatch.setenv("OLLAMA_THINK", "true")
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.2")

    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    config = AppConfig.load(str(env_file))

    assert config.ollama_num_ctx == 8192
    assert config.ollama_num_predict == 128
    assert config.ollama_keep_alive == "15m"
    assert config.ollama_think is True
    assert config.ollama_temperature == 0.2


def test_batch_performance_defaults(monkeypatch, tmp_path):
    for name in [
        "TRANSLATION_BATCH_ENABLED",
        "TRANSLATION_BATCH_SIZE",
        "TRANSLATION_BATCH_MAX_CHARS",
        "OLLAMA_BATCH_NUM_PREDICT",
    ]:
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    config = AppConfig.load(str(env_file))

    assert config.translation_batch_enabled is True
    assert config.translation_batch_size == 8
    assert config.translation_batch_max_chars == 6000
    assert config.ollama_batch_num_predict == 1024


def test_phase516_context_defaults(monkeypatch, tmp_path):
    for name in [
        "OLLAMA_FALLBACK_MODEL",
        "CONTEXT_FALLBACK_ENABLED",
        "CONTEXT_ALLOW_LEGACY_TM",
        "STATE_DB",
        "PROMPT_VERSION",
    ]:
        monkeypatch.delenv(name, raising=False)

    env_file = tmp_path / "empty.env"
    env_file.write_text("", encoding="utf-8")
    config = AppConfig.load(str(env_file))

    assert config.ollama_fallback_model == ""
    assert config.context_fallback_enabled is True
    assert config.context_allow_legacy_tm is False
    assert config.prompt_version == "phase5165-v1"
    assert config.state_db.name == "phase5165.db"
    assert config.standard_terminology_file.name == "food_science_standards.yaml"
