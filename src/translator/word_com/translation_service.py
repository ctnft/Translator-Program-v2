from __future__ import annotations

import hashlib
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from translator.powerpoint_com.semantic_blocks import SemanticTextBlock
from translator.progress import TranslationProgressStore
from translator.translation.engine import TranslationEngine, TranslationRequest

from .adapter import WordComAdapter
from .intelligence import WordAnalysis, WordDocumentAnalyzer
from .walker import WordWalker

WORD_TRANSLATION_VERSION = "phase522-word-performance-v1"
_TIME_CELL = re.compile(r"^\s*\d{1,2}[.:]\d{2}\s*$")
_NUMBER_CELL = re.compile(r"^\s*\d+(?:[.,]\d+)?\s*$")


class WordTranslationService:
    def __init__(
        self,
        *,
        engine: TranslationEngine,
        progress: TranslationProgressStore,
        output_dir: str | Path | None = None,
        adapter: WordComAdapter | None = None,
        walker: WordWalker | None = None,
        analyzer: WordDocumentAnalyzer | None = None,
        save_batch_size: int = 20,
        smart_eligibility: bool = True,
    ):
        self.engine = engine
        self.progress = progress
        self.output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
        self.adapter = adapter or WordComAdapter()
        self.walker = walker or WordWalker()
        self.analyzer = analyzer or WordDocumentAnalyzer()
        self.save_batch_size = max(1, int(save_batch_size))
        self.smart_eligibility = bool(smart_eligibility)

    @staticmethod
    def document_id(source_path: Path) -> str:
        stat = source_path.stat()
        payload = f"{source_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}|word-phase522"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _ordered(elements: list[Any]) -> list[Any]:
        story_rank = {"main": 0}
        return sorted(
            elements,
            key=lambda e: (
                story_rank.get(e.story, 10),
                e.section_index or 0,
                e.range_start if e.range_start is not None else 10**12,
                e.table_index or 0,
                e.cell_index or 0,
                e.shape_index or 0,
            ),
        )

    @staticmethod
    def _table_contexts(elements: list[Any]) -> dict[str, dict[str, Any]]:
        groups: dict[int, list[Any]] = defaultdict(list)
        for e in elements:
            if e.kind == "table_cell" and e.table_index is not None:
                groups[e.table_index].append(e)
        contexts: dict[str, dict[str, Any]] = {}
        for cells in groups.values():
            by_pos = {(c.row, c.column): c for c in cells if c.row is not None and c.column is not None}
            rows = sorted({c.row for c in cells if c.row is not None})
            cols = sorted({c.column for c in cells if c.column is not None})
            for cell in cells:
                row, col = cell.row, cell.column
                if row is None or col is None:
                    continue
                row_cells = [by_pos[(row, c)].text for c in cols if (row, c) in by_pos]
                below = [by_pos[(r, col)].text for r in rows if r > row and (r, col) in by_pos][:8]
                normalized = re.sub(r"[.\s]+$", "", cell.text.strip().casefold())
                row_norm = {re.sub(r"[.\s]+$", "", value.strip().casefold()) for value in row_cells}
                time_below = sum(1 for value in below if _TIME_CELL.fullmatch(value or ""))
                number_below = sum(1 for value in below if _NUMBER_CELL.fullmatch(value or ""))
                hint = preferred = reason = ""
                if normalized == "stop" and "start" in row_norm and time_below >= 1:
                    hint, preferred = "schedule_end_time_header", "Selesai"
                    reason = "Stop paired with Start and schedule times below."
                elif normalized == "no" and number_below >= 2:
                    hint, preferred = "sequence_number_header", "No."
                    reason = "No/No. is a numeric sequence header."
                contexts[WordWalker.element_key(cell)] = {
                    "table_index": cell.table_index,
                    "row": row,
                    "column": col,
                    "row_cells": row_cells,
                    "column_values_below": below,
                    "semantic_hint": hint,
                    "preferred_translation": preferred,
                    "hint_reason": reason,
                }
        return contexts

    @staticmethod
    def _context_payload(
        analysis: WordAnalysis,
        element: Any,
        *,
        previous_text: str,
        next_text: str,
        table_context: dict[str, Any] | None,
    ) -> str:
        key = WordWalker.element_key(element)
        info = analysis.elements[key]
        # Keep per-element context compact. TranslationEngine already sends document_context,
        # expert profile and full_element_text outside slide_context. Repeating those for every
        # Word paragraph was forcing 2-4 elements per Ollama batch even when batch_size=8.
        compact_table = dict(table_context or {})
        if compact_table:
            compact_table["row_cells"] = [str(v)[:160] for v in compact_table.get("row_cells", [])[:8]]
            compact_table["column_values_below"] = [
                str(v)[:80] for v in compact_table.get("column_values_below", [])[:6]
            ]
        payload = {
            "word_structure": {
                "element_kind": element.kind,
                "story": element.story,
                "style": element.style_name,
                "outline_level": element.outline_level,
                "heading_path": list(element.heading_path)[-4:],
                "page_number": element.page_number,
                "previous_text": previous_text[:280],
                "next_text": next_text[:280],
            },
            "protected_brand_entities": info.protected_entities[:12],
            "table_context": compact_table,
            "instruction": (
                "Word element only. Use heading/neighbors/table only for disambiguation; translate no context text. "
                "Preserve brands, identifiers, numbers, formulas and units."
            ),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _analysis_summary(self, analysis: WordAnalysis) -> dict[str, Any]:
        roles: dict[str, int] = defaultdict(int)
        policies: dict[str, int] = defaultdict(int)
        ambiguous = 0
        for item in analysis.elements.values():
            roles[item.semantic_role] += 1
            policies[item.translate_policy] += 1
            ambiguous += int(item.ambiguous)
        return {
            "profile": analysis.profile.to_dict(),
            "semantic_roles": dict(sorted(roles.items())),
            "translation_policies": dict(sorted(policies.items())),
            "ambiguous_elements": ambiguous,
        }

    @staticmethod
    def _progress_record(
        document_id: str,
        element_key: str,
        source_text: str,
        target_text: str,
        status: str,
        origin: str,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "document_id": document_id,
            "element_key": element_key,
            "source_text": source_text,
            "target_text": target_text,
            "status": status,
            "origin": origin,
            "error": error,
            "translation_version": WORD_TRANSLATION_VERSION,
        }

    def translate(
        self,
        *,
        source_path: str | None = None,
        output_path: str | None = None,
        start_element: int = 1,
        end_element: int | None = None,
        resume: bool = False,
        apply: bool = False,
    ) -> dict[str, Any]:
        total_started = time.perf_counter()
        timings = {
            "attach_open_seconds": 0.0,
            "inspect_seconds": 0.0,
            "analysis_seconds": 0.0,
            "copy_open_target_seconds": 0.0,
            "translation_seconds": 0.0,
            "write_seconds": 0.0,
            "save_seconds": 0.0,
            "checkpoint_seconds": 0.0,
            "structure_verify_seconds": 0.0,
        }
        save_calls = 0
        checkpoint_batch_commits = 0

        t0 = time.perf_counter()
        app = self.adapter.attach_application()
        source_doc = self.adapter.get_document(app, source_path)
        source_file = self.adapter.ensure_saved_source(source_doc)
        timings["attach_open_seconds"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        source_stats, all_elements = self.walker.inspect(source_doc)
        ordered = self._ordered(all_elements)
        timings["inspect_seconds"] = time.perf_counter() - t0

        expert_role = self.engine.expert_profile.role if self.engine.expert_profile else "technical localization reviewer"
        domain_style = (
            f"Bahasa Indonesia profesional dan natural untuk domain {self.engine.domain}; "
            f"gunakan judgement {expert_role}; pertahankan identifier, angka, formula, unit, dan istilah yang memang harus tetap."
        )
        t0 = time.perf_counter()
        analysis = self.analyzer.analyze(
            source_stats,
            ordered,
            domain=self.engine.domain,
            style=domain_style,
            smart_eligibility=self.smart_eligibility,
        )
        table_contexts = self._table_contexts(ordered)
        timings["analysis_seconds"] = time.perf_counter() - t0
        self.engine.configure_document_context(
            summary=analysis.profile.summary(),
            preserve_phrases=analysis.profile.preserve_phrases,
        )

        if start_element < 1:
            raise ValueError("--start-element minimal 1")
        last = len(ordered) if end_element is None else min(len(ordered), end_element)
        if ordered and start_element > last:
            raise ValueError(f"Element range tidak valid: {start_element}-{last}")
        selected = ordered[start_element - 1 : last]
        selected_translate = sum(
            1 for e in selected if analysis.elements[WordWalker.element_key(e)].translate_policy == "translate"
        )
        smart_skip_reasons: dict[str, int] = defaultdict(int)
        for e in selected:
            info = analysis.elements[WordWalker.element_key(e)]
            for reason in info.reasons:
                if reason.startswith("smart_skip_"):
                    smart_skip_reasons[reason] += 1

        plan = {
            "document": source_stats.document_name,
            "element_count": len(ordered),
            "selected_element_range": [start_element, last],
            "selected_elements": len(selected),
            "selected_translatable_elements": selected_translate,
            "selected_preserved_elements": len(selected) - selected_translate,
            "smart_eligibility_enabled": self.smart_eligibility,
            "smart_skip_reasons": dict(sorted(smart_skip_reasons.items())),
            "word_save_batch_size": self.save_batch_size,
            "stats": source_stats.to_dict(),
            "document_intelligence": self._analysis_summary(analysis),
            "supported_surfaces": ["paragraph", "table_cell", "header", "footer", "textbox"],
            "preserve_policy": [
                "word_fields", "content_controls", "detected_brand_entities",
                "numeric_or_unit_only", "identifier_only", "already_indonesian_when_confident",
            ],
        }
        if not apply:
            timings["total_seconds"] = time.perf_counter() - total_started
            return {
                "phase": "5.2.2",
                "mode": "plan_only",
                "source_path": str(source_file),
                "model": self.engine.model,
                "fallback_model": self.engine.fallback_model or None,
                "plan": plan,
                "performance": {"timings": timings},
                "note": "Belum ada file diubah. Tambahkan --apply untuk menerjemahkan copy DOCX.",
            }

        if output_path is None:
            base = self.output_dir or source_file.parent
            output_path = str(base / f"{source_file.stem}_ID_PHASE522.docx")

        t0 = time.perf_counter()
        before_structure = self.walker.structure_snapshot(source_doc)
        target_doc, target_path = self.adapter.open_or_create_translation_copy(
            app, source_doc, output_path, resume=resume
        )
        timings["copy_open_target_seconds"] = time.perf_counter() - t0

        source_track_revisions = getattr(source_doc, "TrackRevisions", None)
        try:
            target_doc.TrackRevisions = False
        except Exception:
            pass

        doc_id = self.document_id(source_file)
        items: list[dict[str, Any]] = []
        completed = written = unchanged = manual_review = preserved = checkpoint_skips = stale = 0
        format_differences: list[str] = []
        pending_records: list[dict[str, Any]] = []
        pending_item_indices: list[int] = []
        checkpoint_replays: list[tuple[Any, str, str, str, int]] = []

        request_elements: list[Any] = []
        requests: list[TranslationRequest] = []
        blocks: list[SemanticTextBlock] = []

        ordered_index = {WordWalker.element_key(e): i for i, e in enumerate(ordered)}

        def save_many(records: list[dict[str, Any]]) -> None:
            nonlocal checkpoint_batch_commits
            if not records:
                return
            started = time.perf_counter()
            self.progress.save_many(records)
            timings["checkpoint_seconds"] += time.perf_counter() - started
            checkpoint_batch_commits += 1

        def save_word() -> None:
            nonlocal save_calls
            started = time.perf_counter()
            self.adapter.save(target_doc)
            timings["save_seconds"] += time.perf_counter() - started
            save_calls += 1

        def flush_pending(*, final: bool = False) -> None:
            """Durable Word/checkpoint commit.

            1) Store target text as pending_save in one SQLite transaction.
            2) Save Word once for the whole batch.
            3) Promote the same rows to completed in one SQLite transaction.

            Resume can safely recover both crash windows by comparing disk text with
            pending target text.
            """
            nonlocal pending_records, pending_item_indices
            if not pending_records:
                return
            pending_rows = [dict(r, status="pending_save") for r in pending_records]
            save_many(pending_rows)
            save_word()
            completed_rows = [dict(r, status="completed") for r in pending_records]
            save_many(completed_rows)
            for item_index in pending_item_indices:
                if 0 <= item_index < len(items):
                    items[item_index]["checkpoint_status"] = "completed"
            pending_records = []
            pending_item_indices = []
            if final:
                print(f"[word-save] final durable batch committed; saves={save_calls}")

        for element in selected:
            key = WordWalker.element_key(element)
            info = analysis.elements[key]
            if info.translate_policy == "preserve":
                preserved += 1
                unchanged += 1
                items.append({
                    "element": key,
                    "status": "preserved_intentionally",
                    "semantic_role": info.semantic_role,
                    "source": element.text,
                    "target": element.text,
                    "reasons": info.reasons,
                })
                continue

            checkpoint = self.progress.get(
                doc_id, key, element.text, translation_version=WORD_TRANSLATION_VERSION
            ) if resume else None
            if checkpoint and checkpoint.get("status") in {"completed", "pending_save"} and checkpoint.get("target_text"):
                current = self.walker.read_element_text(target_doc, element)
                target_text = str(checkpoint["target_text"])
                if current == target_text:
                    if checkpoint.get("status") == "pending_save":
                        save_many([self._progress_record(
                            doc_id, key, element.text, target_text, "completed", checkpoint.get("origin") or "checkpoint"
                        )])
                    checkpoint_skips += 1
                    items.append({
                        "element": key,
                        "status": "already_applied",
                        "origin": checkpoint.get("origin"),
                        "recovered_pending_checkpoint": checkpoint.get("status") == "pending_save",
                    })
                    continue
                if current == element.text:
                    try:
                        started = time.perf_counter()
                        write_result = self.walker.replace_text(target_doc, element, target_text)
                        timings["write_seconds"] += time.perf_counter() - started
                        item_idx = len(items)
                        items.append({
                            "element": key,
                            "status": "completed_from_checkpoint",
                            "origin": checkpoint.get("origin") or "checkpoint",
                            "target": target_text,
                            "checkpoint_status": "pending_save",
                        })
                        pending_records.append(self._progress_record(
                            doc_id, key, element.text, target_text, "completed", checkpoint.get("origin") or "checkpoint"
                        ))
                        pending_item_indices.append(item_idx)
                        written += 1
                        checkpoint_skips += 1
                        if len(pending_records) >= self.save_batch_size:
                            flush_pending()
                        continue
                    except Exception as exc:
                        manual_review += 1
                        items.append({"element": key, "status": "manual_review", "error": str(exc)})
                        continue
                manual_review += 1
                items.append({"element": key, "status": "manual_review", "error": "Resume conflict pada Word range."})
                continue

            block = SemanticTextBlock.encode(element.text)
            idx = ordered_index[key]
            prev_text = ordered[idx - 1].text if idx > 0 else ""
            next_text = ordered[idx + 1].text if idx + 1 < len(ordered) else ""
            table_ctx = table_contexts.get(key, {})
            request_elements.append(element)
            blocks.append(block)
            requests.append(
                TranslationRequest(
                    text=block.encoded_text,
                    slide_context=self._context_payload(
                        analysis, element, previous_text=prev_text, next_text=next_text, table_context=table_ctx
                    ),
                    context_key=info.context_key,
                    semantic_role=info.semantic_role,
                    ambiguous=info.ambiguous,
                    preserve=False,
                    element_key=key,
                    full_element_text=block.flattened_text,
                    structural_hint=table_ctx.get("semantic_hint", ""),
                    preferred_translation=table_ctx.get("preferred_translation", ""),
                    line_segments=block.line_segments,
                    break_tokens=block.break_tokens,
                )
            )

        # Flush checkpoint replays before starting new model work. Usually this is zero;
        # after a crash it converts up to save_batch_size recovered writes with one Word save.
        flush_pending()

        t0 = time.perf_counter()
        results = self.engine.translate_many(requests) if requests else []
        timings["translation_seconds"] = time.perf_counter() - t0

        for index, element in enumerate(request_elements):
            key = WordWalker.element_key(element)
            info = analysis.elements[key]
            result = results[index] if index < len(results) else None
            if result is None or result.status == "manual_review":
                error = (result.error if result else "Translation result tidak ditemukan") or "Translation failed"
                manual_review += 1
                save_many([self._progress_record(
                    doc_id, key, element.text, element.text, "manual_review", "translation", error
                )])
                items.append({"element": key, "status": "manual_review", "semantic_role": info.semantic_role, "error": error})
                continue
            try:
                target_text = blocks[index].decode(result.target_text)
            except Exception as exc:
                manual_review += 1
                save_many([self._progress_record(
                    doc_id, key, element.text, element.text, "manual_review", "decode", str(exc)
                )])
                items.append({"element": key, "status": "manual_review", "error": str(exc)})
                continue

            if target_text.strip() == element.text.strip():
                unchanged += 1
                save_many([self._progress_record(
                    doc_id, key, element.text, target_text, "skipped_no_change", result.origin
                )])
                items.append({
                    "element": key, "status": "skipped_no_change", "origin": result.origin,
                    "source": element.text, "target": target_text,
                })
                continue

            try:
                started = time.perf_counter()
                write_result = self.walker.replace_text(target_doc, element, target_text)
                timings["write_seconds"] += time.perf_counter() - started
                if write_result["text"] != target_text:
                    raise ValueError(f"Post-write mismatch: {write_result['text']!r} != {target_text!r}")
                if write_result["style_before"] != write_result["style_after"]:
                    format_differences.append(
                        f"{key} style changed: {write_result['style_before']!r} -> {write_result['style_after']!r}"
                    )
                before_styles = write_result.get("font_style_sequence_before") or []
                after_styles = write_result.get("font_style_sequence_after") or []
                if before_styles and after_styles and before_styles != after_styles:
                    format_differences.append(f"{key} font style sequence changed")

                item_idx = len(items)
                items.append({
                    "element": key,
                    "status": "completed",
                    "origin": result.origin,
                    "semantic_role": info.semantic_role,
                    "source": element.text,
                    "target": target_text,
                    "quality_warnings": list(result.quality_warnings),
                    "checkpoint_status": "pending_save",
                })
                pending_records.append(self._progress_record(
                    doc_id, key, element.text, target_text, "completed", result.origin
                ))
                pending_item_indices.append(item_idx)
                completed += 1
                written += 1
                print(f"[word {written}/{selected_translate}] {key} [{info.semantic_role}] -> {result.origin}")
                if len(pending_records) >= self.save_batch_size:
                    flush_pending()
            except Exception as exc:
                manual_review += 1
                save_many([self._progress_record(
                    doc_id, key, element.text, target_text, "manual_review", "writer", str(exc)
                )])
                items.append({"element": key, "status": "manual_review", "semantic_role": info.semantic_role, "error": str(exc)})

        # Restore the source setting before the final durable save so the output does
        # not permanently inherit the temporary TrackRevisions=False state.
        had_final_pending = bool(pending_records)
        try:
            if source_track_revisions is not None:
                target_doc.TrackRevisions = source_track_revisions
        except Exception:
            pass
        flush_pending(final=True)
        # If the last translation batch was already flushed earlier, TrackRevisions
        # restoration has not yet been persisted. Save it once when the source had
        # Track Changes enabled.
        if not had_final_pending and bool(source_track_revisions):
            save_word()

        t0 = time.perf_counter()
        after_structure = self.walker.structure_snapshot(target_doc)
        integrity = self.walker.compare_structure(before_structure, after_structure)
        timings["structure_verify_seconds"] = time.perf_counter() - t0
        self.adapter.activate_document_window(target_doc)

        analysis_path = target_path.with_suffix(".phase522-analysis.json")
        analysis_path.write_text(json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        timings["total_seconds"] = time.perf_counter() - total_started
        report = {
            "phase": "5.2.2",
            "adapter": "word_com_docx",
            "source_path": str(source_file),
            "output_path": str(target_path),
            "document_id": doc_id,
            "model": self.engine.model,
            "fallback_model": self.engine.fallback_model or None,
            "element_range": [start_element, last],
            "selected_elements": len(selected),
            "selected_translatable_elements": selected_translate,
            "selected_preserved_elements": len(selected) - selected_translate,
            "completed_this_run": completed,
            "written_this_run": written,
            "checkpoint_skips": checkpoint_skips,
            "stale_checkpoint_ignored": stale,
            "preserved_intentionally": preserved,
            "unchanged_elements": unchanged,
            "manual_review": manual_review,
            "document_stats": source_stats.to_dict(),
            "document_intelligence": self._analysis_summary(analysis),
            "analysis_path": str(analysis_path),
            "translation_stats": dict(self.engine.stats),
            "expert_profile": self.engine.expert_profile.to_prompt_dict() if self.engine.expert_profile else {},
            "word_performance": {
                "smart_eligibility_enabled": self.smart_eligibility,
                "smart_skip_reasons": dict(sorted(smart_skip_reasons.items())),
                "save_batch_size": self.save_batch_size,
                "word_save_calls": save_calls,
                "checkpoint_batch_commits": checkpoint_batch_commits,
                "ollama_requests_prepared": len(requests),
                "ollama_batch_calls": self.engine.stats.get("batch_calls", 0),
                "ollama_single_calls": self.engine.stats.get("ollama_single_calls", 0),
                "timings_seconds": {k: round(v, 4) for k, v in timings.items()},
            },
            "word_format_preservation": {
                "strict_text_only": True,
                "source_never_overwritten": True,
                "track_revisions_disabled_during_write": True,
                "paragraph_marks_not_replaced": True,
                "table_cell_marks_not_replaced": True,
                "font_runs_restored": True,
                "paragraph_format_restored": True,
                "table_dimensions_restored": True,
                "format_differences": format_differences,
                "passed": not format_differences,
            },
            "checkpoint_reliability": {
                "strategy": "pending_save -> batched Word Save -> completed",
                "resume_recovers_pending_save": True,
                "save_batch_size": self.save_batch_size,
            },
            "zero_untranslated_recovery": {
                "enabled": self.engine.recovery_enabled,
                "unresolved_translatable_elements": manual_review,
                "passed": manual_review == 0,
            },
            "structure_integrity": integrity.to_dict(),
            "manual_visual_check_required": True,
            "items": items,
            "warnings": (
                ([f"ZERO-UNTRANSLATED GATE FAILED: {manual_review} Word element unresolved."] if manual_review else [])
                + (["FORMAT PRESERVATION WARNING: satu atau lebih style/font sequence berubah."] if format_differences else [])
            ),
        }
        report_path = target_path.with_suffix(".phase522-report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        return report
