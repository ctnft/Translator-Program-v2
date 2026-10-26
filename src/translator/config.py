from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"Environment variable {name} harus boolean: true/false, yes/no, on/off, atau 1/0."
    )


def _project_path(value: str | None, default: str) -> Path:
    path = Path((value or default).strip()).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


@dataclass(frozen=True)
class AppConfig:
    ollama_base_url: str
    ollama_model: str
    ollama_fallback_model: str
    source_lang: str
    target_lang: str
    domain: str
    ollama_timeout_seconds: float
    ollama_retries: int
    ollama_num_ctx: int
    ollama_num_predict: int
    ollama_keep_alive: str
    ollama_think: bool
    ollama_temperature: float
    translation_batch_enabled: bool
    translation_batch_size: int
    translation_batch_max_chars: int
    ollama_batch_num_predict: int
    context_fallback_enabled: bool
    context_allow_legacy_tm: bool
    zero_untranslated_recovery_enabled: bool
    prompt_version: str
    expert_profile: str
    expert_profile_file: Path
    terminology_file: Path
    standard_terminology_file: Path
    state_db: Path
    word_state_db: Path
    word_save_batch_size: int
    word_smart_eligibility: bool
    tm_db: Path
    cache_db: Path
    input_dir: Path
    output_dir: Path

    @classmethod
    def load(cls, env_file: str | None = None) -> "AppConfig":
        load_dotenv(env_file or str(PROJECT_ROOT / ".env"), override=False)
        config = cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "").strip(),
            ollama_fallback_model=os.getenv("OLLAMA_FALLBACK_MODEL", "").strip(),
            source_lang=os.getenv("SOURCE_LANG", "en").strip(),
            target_lang=os.getenv("TARGET_LANG", "id").strip(),
            domain=os.getenv("TRANSLATION_DOMAIN", "food_science").strip(),
            ollama_timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "300")),
            ollama_retries=max(1, int(os.getenv("OLLAMA_RETRIES", "1"))),
            ollama_num_ctx=max(1024, int(os.getenv("OLLAMA_NUM_CTX", "4096"))),
            ollama_num_predict=max(32, int(os.getenv("OLLAMA_NUM_PREDICT", "256"))),
            ollama_keep_alive=os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m",
            ollama_think=_env_bool("OLLAMA_THINK", False),
            ollama_temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0")),
            translation_batch_enabled=_env_bool("TRANSLATION_BATCH_ENABLED", True),
            translation_batch_size=max(1, int(os.getenv("TRANSLATION_BATCH_SIZE", "8"))),
            translation_batch_max_chars=max(500, int(os.getenv("TRANSLATION_BATCH_MAX_CHARS", "6000"))),
            ollama_batch_num_predict=max(128, int(os.getenv("OLLAMA_BATCH_NUM_PREDICT", "1024"))),
            context_fallback_enabled=_env_bool("CONTEXT_FALLBACK_ENABLED", True),
            context_allow_legacy_tm=_env_bool("CONTEXT_ALLOW_LEGACY_TM", False),
            zero_untranslated_recovery_enabled=_env_bool("ZERO_UNTRANSLATED_RECOVERY", True),
            prompt_version=os.getenv("PROMPT_VERSION", "phase51611-v1").strip(),
            expert_profile=os.getenv("EXPERT_PROFILE", "sensory_training_food_scientist").strip(),
            expert_profile_file=_project_path(os.getenv("EXPERT_PROFILE_FILE"), "expert_profiles.yaml"),
            terminology_file=_project_path(os.getenv("TERMINOLOGY_FILE"), "terminology.yaml"),
            standard_terminology_file=_project_path(os.getenv("STANDARD_TERMINOLOGY_FILE"), "food_science_standards.yaml"),
            state_db=_project_path(os.getenv("STATE_DB"), ".translator_state/phase51611.db"),
            word_state_db=_project_path(os.getenv("WORD_STATE_DB"), ".translator_state/phase522-word.db"),
            word_save_batch_size=max(1, int(os.getenv("WORD_SAVE_BATCH_SIZE", "20"))),
            word_smart_eligibility=_env_bool("WORD_SMART_ELIGIBILITY", True),
            tm_db=_project_path(os.getenv("TM_DB"), ".translator_state/translation_memory.db"),
            cache_db=_project_path(os.getenv("CACHE_DB"), ".translator_state/translation_cache.db"),
            input_dir=_project_path(os.getenv("INPUT_DIR"), "input"),
            output_dir=_project_path(os.getenv("OUTPUT_DIR"), "output"),
        )
        config.input_dir.mkdir(parents=True, exist_ok=True)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        return config
