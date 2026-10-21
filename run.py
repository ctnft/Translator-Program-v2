from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from translator.cache_manager import CacheManager
from translator.config import AppConfig
from translator.ollama.client import OllamaClient, OllamaError
from translator.powerpoint_com.errors import PowerPointComError
from translator.powerpoint_com.poc import PowerPointPocService
from translator.powerpoint_com.intelligence_service import PowerPointIntelligenceService
from translator.powerpoint_com.translation_service import PowerPointTranslationService
from translator.progress import TranslationProgressStore
from translator.terminology_lock import TerminologyLock
from translator.translation.engine import TranslationEngine
from translator.translation_memory import TranslationMemory
from translator.yaml_loader import TerminologyLoader


def _print_report(report: dict) -> None:
    print(json.dumps(report, ensure_ascii=False, indent=2))


def _resolve_source_path(value: str | None, config: AppConfig) -> str | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config.input_dir / path
    return str(path.resolve())


def _resolve_output_path(value: str | None, config: AppConfig) -> str | None:
    if value is None:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = config.output_dir / path
    return str(path.resolve())


def _build_ollama_client(config: AppConfig) -> OllamaClient:
    return OllamaClient(
        base_url=config.ollama_base_url,
        timeout_seconds=config.ollama_timeout_seconds,
        retries=config.ollama_retries,
        num_ctx=config.ollama_num_ctx,
        num_predict=config.ollama_num_predict,
        keep_alive=config.ollama_keep_alive,
        think=config.ollama_think,
        temperature=config.ollama_temperature,
    )


def _build_engine(config: AppConfig, model_override: str | None = None) -> TranslationEngine:
    loader = TerminologyLoader()
    standard_data = loader.load(config.standard_terminology_file)
    custom_data = loader.load(config.terminology_file)
    terminology_data = loader.merge(standard_data, custom_data)
    model = (model_override or config.ollama_model).strip()
    client = _build_ollama_client(config)
    return TranslationEngine(
        client=client,
        model=model,
        translation_memory=TranslationMemory(config.tm_db),
        cache=CacheManager(config.cache_db),
        terminology=TerminologyLock(terminology_data["terms"]),
        domain=str(terminology_data.get("domain") or config.domain),
        source_lang=config.source_lang,
        target_lang=config.target_lang,
        prompt_version=config.prompt_version,
        terminology_version=str(terminology_data.get("version", "1.0")),
        batch_enabled=config.translation_batch_enabled,
        batch_size=config.translation_batch_size,
        batch_max_chars=config.translation_batch_max_chars,
        batch_num_predict=config.ollama_batch_num_predict,
        fallback_model=config.ollama_fallback_model,
        fallback_enabled=config.context_fallback_enabled,
        allow_legacy_tm=config.context_allow_legacy_tm,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Translator Program local PowerPoint integration")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ppt-inspect", help="Attach ke PowerPoint aktif dan baca struktur dasar presentasi.")

    analyze = sub.add_parser(
        "ppt-analyze",
        help="Phase 5.1.6.5: full-deck document intelligence tanpa menerjemahkan.",
    )
    analyze.add_argument("--source", help="Nama/path source PPTX. Path relatif dibaca dari folder input/.")

    replace = sub.add_parser("ppt-replace-one", help="Buat copy presentasi aktif lalu ganti SATU teks pada copy.")
    replace.add_argument("--find", required=True, help="Teks yang dicari.")
    replace.add_argument("--replace", required=True, help="Teks pengganti.")
    replace.add_argument("--output", help="Path output PPTX copy.")
    replace.add_argument("--match-case", action="store_true")
    replace.add_argument("--whole-words", action="store_true")

    check = sub.add_parser("ollama-check", help="Cek koneksi Ollama dan daftar model lokal.")
    check.add_argument("--model", help="Model yang ingin diverifikasi; override OLLAMA_MODEL.")

    smoke = sub.add_parser("ollama-smoke", help="Uji structured generation Ollama dengan konfigurasi runtime translator.")
    smoke.add_argument("--model", help="Model yang diuji; override OLLAMA_MODEL.")

    translate = sub.add_parser(
        "ppt-translate",
        help="Phase 5.1.6.5: context-aware PPTX translation melalui COM + document intelligence + TM + Ollama.",
    )
    translate.add_argument("--source", help="Nama/path source PPTX. Path relatif dibaca dari folder input/.")
    translate.add_argument("--output", help="Nama/path output. Path relatif ditulis ke folder output/. Default: output/<source>_ID_PHASE5165.pptx")
    translate.add_argument("--model", help="Override OLLAMA_MODEL dari .env")
    translate.add_argument("--start-slide", type=int, default=1)
    translate.add_argument("--end-slide", type=int)
    translate.add_argument("--all-slides", action="store_true", help="Translate sampai slide terakhir.")
    translate.add_argument("--max-elements", type=int, default=0, help="0 = tanpa limit dalam range slide.")
    translate.add_argument("--resume", action="store_true", help="Lanjutkan output/checkpoint yang sudah ada.")
    translate.add_argument("--apply", action="store_true", help="Wajib untuk benar-benar memanggil Ollama dan menulis copy PPTX.")
    translate.add_argument("--batch-size", type=int, help="Override jumlah segmen unik per batch Ollama untuk run ini.")
    translate.add_argument("--no-batch", action="store_true", help="Matikan batching dan gunakan jalur single-segment legacy.")

    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        if args.command == "ppt-inspect":
            _print_report(PowerPointPocService().inspect_active())
            return 0

        if args.command == "ppt-replace-one":
            report = PowerPointPocService().replace_one_on_copy(
                find_text=args.find,
                replace_text=args.replace,
                output_path=args.output,
                match_case=args.match_case,
                whole_words=args.whole_words,
            )
            _print_report(report)
            return 0 if report["structure_integrity"]["passed"] else 2

        config = AppConfig.load()

        if args.command == "ppt-analyze":
            service = PowerPointIntelligenceService(output_dir=config.output_dir)
            report = service.analyze(source_path=_resolve_source_path(args.source, config))
            _print_report(report)
            return 0

        if args.command == "ollama-check":
            client = _build_ollama_client(config)
            models = client.list_models()
            requested = (args.model or config.ollama_model).strip()
            _print_report({
                "base_url": config.ollama_base_url,
                "models": models,
                "requested_model": requested or None,
                "requested_model_available": (requested in models) if requested else None,
                "fallback_model": config.ollama_fallback_model or None,
                "fallback_model_available": (config.ollama_fallback_model in models) if config.ollama_fallback_model else None,
                "runtime": {
                    "timeout_seconds": config.ollama_timeout_seconds,
                    "retries": config.ollama_retries,
                    "num_ctx": config.ollama_num_ctx,
                    "num_predict": config.ollama_num_predict,
                    "keep_alive": config.ollama_keep_alive,
                    "think": config.ollama_think,
                    "temperature": config.ollama_temperature,
                    "batch_enabled": config.translation_batch_enabled,
                    "batch_size": config.translation_batch_size,
                    "batch_max_chars": config.translation_batch_max_chars,
                    "batch_num_predict": config.ollama_batch_num_predict,
                    "context_fallback_enabled": config.context_fallback_enabled,
                    "context_allow_legacy_tm": config.context_allow_legacy_tm,
                },
            })
            return 0 if (not requested or requested in models) else 2

        if args.command == "ollama-smoke":
            client = _build_ollama_client(config)
            model = (args.model or config.ollama_model).strip()
            if not model:
                raise OllamaError("Model belum ditentukan. Isi OLLAMA_MODEL di .env atau gunakan --model.")
            models = client.list_models()
            if model not in models:
                raise OllamaError(f"Model {model!r} tidak ditemukan. Model lokal: {models}")
            print(f"[ollama-smoke] testing {model!r}...")
            probe = client.generation_probe(model=model)
            _print_report({
                "model": model,
                "status": "ok",
                "runtime": {
                    "num_ctx": config.ollama_num_ctx,
                    "num_predict": config.ollama_num_predict,
                    "keep_alive": config.ollama_keep_alive,
                    "think": config.ollama_think,
                    "temperature": config.ollama_temperature,
                    "batch_enabled": config.translation_batch_enabled,
                    "batch_size": config.translation_batch_size,
                    "batch_max_chars": config.translation_batch_max_chars,
                    "batch_num_predict": config.ollama_batch_num_predict,
                    "context_fallback_enabled": config.context_fallback_enabled,
                    "context_allow_legacy_tm": config.context_allow_legacy_tm,
                },
                "probe": probe,
                "metrics": client.last_metrics,
            })
            return 0

        if args.command == "ppt-translate":
            engine = _build_engine(config, args.model)
            if args.no_batch:
                engine.batch_enabled = False
            if args.batch_size is not None:
                if args.batch_size < 1:
                    raise ValueError("--batch-size minimal 1")
                engine.batch_size = args.batch_size
            if args.apply:
                if not engine.model:
                    raise OllamaError("Model belum ditentukan. Isi OLLAMA_MODEL di .env atau gunakan --model.")
                models = engine.client.list_models()
                if engine.model not in models:
                    raise OllamaError(f"Model {engine.model!r} tidak ditemukan. Model lokal: {models}")
                if engine.fallback_enabled and engine.fallback_model and engine.fallback_model not in models:
                    raise OllamaError(
                        f"Fallback model {engine.fallback_model!r} tidak ditemukan. Model lokal: {models}"
                    )
                print(f"[preflight] Ollama model {engine.model!r} ditemukan. Menguji generation...")
                engine.client.generation_probe(model=engine.model)

            service = PowerPointTranslationService(
                engine=engine,
                progress=TranslationProgressStore(config.state_db),
                output_dir=config.output_dir,
            )
            end_slide = None if args.all_slides else (args.end_slide or args.start_slide)
            report = service.translate_active(
                source_path=_resolve_source_path(args.source, config),
                output_path=_resolve_output_path(args.output, config),
                start_slide=args.start_slide,
                end_slide=end_slide,
                max_elements=args.max_elements or None,
                resume=args.resume,
                apply=args.apply,
            )
            _print_report(report)
            if args.apply and not report["structure_integrity"]["passed"]:
                return 2
            return 0

    except (PowerPointComError, OllamaError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
