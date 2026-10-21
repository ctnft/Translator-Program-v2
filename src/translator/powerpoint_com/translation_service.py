from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from translator.document_intelligence.analyzer import DocumentIntelligenceAnalyzer
from translator.document_intelligence.models import DeckAnalysis
from translator.progress import TranslationProgressStore
from translator.translation.engine import (
    TRANSLATION_POLICY_VERSION,
    TranslationEngine,
    TranslationRequest,
    TranslationResult,
)
from .adapter import PowerPointComAdapter
from .semantic_blocks import SemanticTextBlock
from .walker import PowerPointWalker


_SEPARATOR = re.compile(r"(\r|\v|\n)")


def split_text_preserving_breaks(text: str) -> list[str]:
    return _SEPARATOR.split(text)


def build_replacement_pairs(source: str, target: str) -> list[tuple[str, str]]:
    src = split_text_preserving_breaks(source)
    dst = split_text_preserving_breaks(target)
    src_seps = [part for part in src if _SEPARATOR.fullmatch(part or "")]
    dst_seps = [part for part in dst if _SEPARATOR.fullmatch(part or "")]
    if src_seps != dst_seps:
        raise ValueError("Struktur line/paragraph break berubah; element ditandai manual_review.")
    src_text = [part for part in src if not _SEPARATOR.fullmatch(part or "")]
    dst_text = [part for part in dst if not _SEPARATOR.fullmatch(part or "")]
    if len(src_text) != len(dst_text):
        raise ValueError("Jumlah semantic segment berubah; element ditandai manual_review.")
    return list(zip(src_text, dst_text))


class PowerPointTranslationService:
    def __init__(
        self,
        *,
        engine: TranslationEngine,
        progress: TranslationProgressStore,
        output_dir: str | Path | None = None,
        adapter: PowerPointComAdapter | None = None,
        walker: PowerPointWalker | None = None,
        analyzer: DocumentIntelligenceAnalyzer | None = None,
    ):
        self.engine = engine
        self.progress = progress
        self.adapter = adapter or PowerPointComAdapter()
        self.walker = walker or PowerPointWalker()
        self.analyzer = analyzer or DocumentIntelligenceAnalyzer()
        self.output_dir = Path(output_dir).expanduser().resolve() if output_dir else None

    @staticmethod
    def document_id(source_path: Path) -> str:
        stat = source_path.stat()
        raw = f"{source_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _context_payload(
        analysis: DeckAnalysis,
        element: Any,
        *,
        segment_index: int,
        segment_count: int,
    ) -> str:
        key = PowerPointWalker.element_key(element)
        info = analysis.elements[key]
        slide = analysis.slides[element.slide_index]
        payload = {
            "document": {
                "type": analysis.profile.document_type,
                "subject": analysis.profile.subject,
                "title": analysis.profile.title,
                "organizations": analysis.profile.organizations[:12],
                "brand_entities": analysis.profile.brand_entities[:40],
                "style": analysis.profile.style,
            },
            "slide": {
                "number": slide.slide_index,
                "role": slide.slide_role,
                "title": slide.title,
                "body": slide.body_text[:18],
                "previous_title": slide.previous_title,
                "next_title": slide.next_title,
            },
            "element": {
                "semantic_role": info.semantic_role,
                "position": info.position_bucket,
                "repetition_count": info.repetition_count,
                "repetition_ratio": info.repetition_ratio,
                "full_element_text": element.text.replace("\v", " / ").replace("\r", " / ").replace("\n", " / "),
                "segment_index": segment_index,
                "segment_count": segment_count,
                "protected_brand_entities": info.protected_entities,
            },
            "instruction": (
                "Treat the complete textbox as one semantic unit. First distinguish category/technical terms from "
                "brand or product names. Protected brand entities must remain exactly unchanged. Translate the "
                "remaining prose with natural Indonesian food-science terminology; avoid word-by-word translation."
            ),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _analysis_summary(self, analysis: DeckAnalysis) -> dict[str, Any]:
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

    def plan(
        self,
        presentation: Any,
        *,
        start_slide: int,
        end_slide: int,
        max_elements: int | None = None,
    ) -> dict[str, Any]:
        stats, elements = self.walker.inspect(presentation)
        analysis = self.analyzer.analyze(stats, elements)
        selected = [e for e in elements if start_slide <= e.slide_index <= end_slide]
        if max_elements and max_elements > 0:
            selected = selected[:max_elements]
        per_slide: dict[int, int] = defaultdict(int)
        for item in selected:
            per_slide[item.slide_index] += 1
        return {
            "presentation": stats.presentation_name,
            "slide_count": stats.slide_count,
            "selected_slide_range": [start_slide, end_slide],
            "selected_elements": len(selected),
            "elements_per_slide": dict(sorted(per_slide.items())),
            "document_intelligence": self._analysis_summary(analysis),
            "batching": {
                "enabled": self.engine.batch_enabled,
                "batch_size": self.engine.batch_size,
                "batch_max_chars": self.engine.batch_max_chars,
                "batch_num_predict": self.engine.batch_num_predict,
            },
            "warnings": stats.warnings,
        }

    def _resume_or_pending(
        self,
        *,
        doc_id: str,
        target: Any,
        element: Any,
        report_items: list[dict[str, Any]],
    ) -> tuple[str, int, int, int, int]:
        key = self.walker.element_key(element)
        existing = self.progress.get(
            doc_id,
            key,
            element.text,
            translation_version=TRANSLATION_POLICY_VERSION,
        )
        if not (existing and existing["status"] == "completed" and existing.get("target_text")):
            return "pending", 0, 0, 0, 0

        target_text = str(existing["target_text"])
        if target_text.strip() == element.text.strip():
            return "pending", 0, 0, 0, 1

        current_text = self.walker.read_element_text(target, element)
        if current_text == target_text:
            report_items.append(
                {"element": key, "status": "already_applied", "origin": existing.get("origin")}
            )
            return "done", 0, 1, 0, 0
        if current_text != element.text:
            report_items.append(
                {
                    "element": key,
                    "status": "manual_review",
                    "error": "Resume conflict: output element berbeda dari source dan checkpoint target.",
                }
            )
            return "done", 0, 0, 1, 0

        try:
            pairs = build_replacement_pairs(element.text, target_text)
            new_text = self.walker.apply_segment_replacements(target, element, pairs)
            if new_text != target_text:
                raise ValueError("Post-write text tidak sama dengan checkpoint target.")
            report_items.append(
                {
                    "element": key,
                    "slide": element.slide_index,
                    "status": "completed_from_checkpoint",
                    "origin": existing.get("origin"),
                    "source": element.text,
                    "target": target_text,
                }
            )
            return "done", 1, 0, 0, 0
        except Exception as exc:
            report_items.append({"element": key, "status": "manual_review", "error": str(exc)})
            return "done", 0, 0, 1, 0

    def translate_active(
        self,
        *,
        source_path: str | None = None,
        output_path: str | None = None,
        start_slide: int = 1,
        end_slide: int | None = None,
        max_elements: int | None = None,
        resume: bool = False,
        apply: bool = False,
    ) -> dict[str, Any]:
        app = self.adapter.attach_application()
        source = self.adapter.get_presentation(app, source_path)
        source_file = self.adapter.ensure_saved_source(source)
        source_stats, elements = self.walker.inspect(source)

        # Phase 5.1.6 requirement: full deck is analyzed before translating any range.
        analysis = self.analyzer.analyze(source_stats, elements)
        self.engine.configure_document_context(
            summary=analysis.profile.summary(),
            preserve_phrases=analysis.profile.preserve_phrases,
        )

        last_slide = source_stats.slide_count if end_slide is None else min(end_slide, source_stats.slide_count)
        if start_slide < 1 or start_slide > last_slide:
            raise ValueError(f"Slide range tidak valid: {start_slide}-{last_slide}")

        selected = [e for e in elements if start_slide <= e.slide_index <= last_slide]
        if max_elements and max_elements > 0:
            selected = selected[:max_elements]

        plan = {
            "presentation": source_stats.presentation_name,
            "slide_count": source_stats.slide_count,
            "selected_slide_range": [start_slide, last_slide],
            "selected_elements": len(selected),
            "document_intelligence": self._analysis_summary(analysis),
            "batching": {
                "enabled": self.engine.batch_enabled,
                "batch_size": self.engine.batch_size,
                "batch_max_chars": self.engine.batch_max_chars,
                "batch_num_predict": self.engine.batch_num_predict,
            },
            "warnings": source_stats.warnings,
        }
        if not apply:
            return {
                "phase": "5.1.6.5",
                "mode": "plan_only",
                "source_path": str(source_file),
                "model": self.engine.model,
                "fallback_model": self.engine.fallback_model or None,
                "plan": plan,
                "note": "Full-deck context sudah dianalisis. Belum ada file yang diubah; tambahkan --apply untuk translation.",
            }

        before_structure = self.walker.structure_snapshot(source)
        resolved_output = output_path
        if resolved_output is None and self.output_dir is not None:
            # New output generation because old Phase 5.1.4/5.1.5 results may contain
            # literal translations that should not be reused by context-aware Phase 5.1.6.
            resolved_output = str(self.output_dir / f"{source_file.stem}_ID_PHASE5165{source_file.suffix}")
        target, target_path = self.adapter.open_or_create_translation_copy(
            app, source, resolved_output, resume=resume
        )
        doc_id = self.document_id(source_file)
        report_items: list[dict[str, Any]] = []
        changed_slide: int | None = None
        completed = 0
        skipped_progress = 0
        manual_review = 0
        written = 0
        unchanged = 0
        contextual_preserved = 0
        stale_checkpoint_ignored = 0

        elements_by_slide: dict[int, list[Any]] = defaultdict(list)
        for element in selected:
            elements_by_slide[element.slide_index].append(element)

        processed_elements = 0
        for slide_index in sorted(elements_by_slide):
            slide_elements = elements_by_slide[slide_index]
            pending: list[Any] = []

            for element in slide_elements:
                key = self.walker.element_key(element)
                intelligence = analysis.elements[key]
                if intelligence.translate_policy == "preserve":
                    contextual_preserved += 1
                    unchanged += 1
                    report_items.append(
                        {
                            "element": key,
                            "slide": element.slide_index,
                            "status": "preserved_by_document_intelligence",
                            "origin": "document_preserve",
                            "semantic_role": intelligence.semantic_role,
                            "source": element.text,
                            "target": element.text,
                            "reasons": intelligence.reasons,
                        }
                    )
                    continue

                state, wrote, chk_skip, manual, stale = self._resume_or_pending(
                    doc_id=doc_id,
                    target=target,
                    element=element,
                    report_items=report_items,
                )
                written += wrote
                skipped_progress += chk_skip
                manual_review += manual
                stale_checkpoint_ignored += stale
                if wrote:
                    changed_slide = element.slide_index
                if state == "pending":
                    pending.append(element)

            if not pending:
                self.adapter.save(target)
                processed_elements += len(slide_elements)
                continue

            # Phase 5.1.6.1: one PowerPoint textbox/cell is one semantic
            # translation unit. Paragraph/soft line breaks are layout boundaries,
            # encoded as immutable markers so mixed font/color lines are not
            # translated independently (which caused duplicated meanings).
            element_requests: list[TranslationRequest] = []
            semantic_blocks: list[SemanticTextBlock] = []

            for element in pending:
                key = self.walker.element_key(element)
                intelligence = analysis.elements[key]
                block = SemanticTextBlock.encode(element.text)
                semantic_blocks.append(block)
                element_requests.append(
                    TranslationRequest(
                        text=block.encoded_text,
                        slide_context=self._context_payload(
                            analysis,
                            element,
                            segment_index=1,
                            segment_count=1,
                        ),
                        context_key=intelligence.context_key,
                        semantic_role=intelligence.semantic_role,
                        ambiguous=intelligence.ambiguous,
                        preserve=False,
                        element_key=key,
                        segment_index=1,
                        segment_count=1,
                        # Give the model the natural phrase without treating each
                        # formatted line as a separate translation request.
                        full_element_text=block.flattened_text,
                    )
                )

            results = self.engine.translate_many(element_requests)

            for element_index, element in enumerate(pending):
                key = self.walker.element_key(element)
                intelligence = analysis.elements[key]
                block = semantic_blocks[element_index]
                result = results[element_index] if element_index < len(results) else None
                origins: list[str] = []
                warnings: list[str] = []
                failed_error: str | None = None

                if result is None:
                    failed_error = "Batch mapping gagal: hasil semantic text block tidak ditemukan."
                    target_text = element.text
                elif result.status == "manual_review":
                    failed_error = result.error or "Translation validation failed"
                    target_text = element.text
                else:
                    origins.append(result.origin)
                    warnings.extend(result.quality_warnings)
                    try:
                        target_text = block.decode(result.target_text)
                    except Exception as exc:
                        failed_error = str(exc)
                        target_text = element.text

                if failed_error is not None:
                    manual_review += 1
                    self.progress.save(
                        doc_id, key, element.text, element.text, "manual_review", "ollama", failed_error,
                        translation_version=TRANSLATION_POLICY_VERSION,
                    )
                    report_items.append(
                        {
                            "element": key,
                            "slide": element.slide_index,
                            "status": "manual_review",
                            "semantic_role": intelligence.semantic_role,
                            "error": failed_error,
                        }
                    )
                    continue

                if target_text.strip() == element.text.strip():
                    unchanged += 1
                    origin = origins[0] if origins and len(set(origins)) == 1 else "mixed"
                    self.progress.save(
                        doc_id, key, element.text, target_text, "skipped_no_change", origin,
                        translation_version=TRANSLATION_POLICY_VERSION,
                    )
                    report_items.append(
                        {
                            "element": key,
                            "slide": element.slide_index,
                            "status": "skipped_no_change",
                            "origin": origin,
                            "semantic_role": intelligence.semantic_role,
                            "source": element.text,
                            "target": target_text,
                            "quality_warnings": sorted(set(warnings)),
                        }
                    )
                    continue

                try:
                    pairs = build_replacement_pairs(element.text, target_text)
                    new_text = self.walker.apply_segment_replacements(target, element, pairs)
                    if new_text != target_text:
                        raise ValueError(f"Post-write mismatch: {new_text!r} != {target_text!r}")
                except Exception as exc:
                    manual_review += 1
                    self.progress.save(
                        doc_id, key, element.text, target_text, "manual_review", "writer", str(exc),
                        translation_version=TRANSLATION_POLICY_VERSION,
                    )
                    report_items.append(
                        {
                            "element": key,
                            "slide": element.slide_index,
                            "status": "manual_review",
                            "semantic_role": intelligence.semantic_role,
                            "error": str(exc),
                        }
                    )
                    continue

                origin = origins[0] if origins and len(set(origins)) == 1 else "mixed"
                self.progress.save(
                    doc_id, key, element.text, target_text, "completed", origin,
                    translation_version=TRANSLATION_POLICY_VERSION,
                )
                completed += 1
                written += 1
                changed_slide = element.slide_index
                report_items.append(
                    {
                        "element": key,
                        "slide": element.slide_index,
                        "status": "completed",
                        "origin": origin,
                        "semantic_role": intelligence.semantic_role,
                        "slide_role": analysis.slides[element.slide_index].slide_role,
                        "source": element.text,
                        "target": target_text,
                        "quality_warnings": sorted(set(warnings)),
                    }
                )
                processed_elements += 1
                print(
                    f"[{processed_elements}/{len(selected)}] slide {element.slide_index} "
                    f"{key} [{intelligence.semantic_role}] -> {origin}"
                )

            self.adapter.save(target)

        after_stats, _ = self.walker.inspect(target)
        integrity = self.walker.compare_structure(before_structure, self.walker.structure_snapshot(target))
        if source_stats.slide_count != after_stats.slide_count:
            integrity.differences.append(
                f"Slide count changed: {source_stats.slide_count} -> {after_stats.slide_count}"
            )
        integrity.passed = not integrity.differences

        self.adapter.activate_presentation_window(target, changed_slide)
        analysis_path = target_path.with_suffix(".phase5165-analysis.json")
        analysis_path.write_text(
            json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        report = {
            "phase": "5.1.6.5",
            "source_path": str(source_file),
            "output_path": str(target_path),
            "document_id": doc_id,
            "model": self.engine.model,
            "fallback_model": self.engine.fallback_model or None,
            "slide_range": [start_slide, last_slide],
            "selected_elements": len(selected),
            "completed_this_run": completed,
            "written_this_run": written,
            "checkpoint_skips": skipped_progress,
            "stale_checkpoint_ignored": stale_checkpoint_ignored,
            "contextual_preserved": contextual_preserved,
            "unchanged_elements": unchanged,
            "manual_review": manual_review,
            "document_intelligence": self._analysis_summary(analysis),
            "analysis_path": str(analysis_path),
            "batching": {
                "enabled": self.engine.batch_enabled,
                "batch_size": self.engine.batch_size,
                "batch_max_chars": self.engine.batch_max_chars,
                "batch_num_predict": self.engine.batch_num_predict,
            },
            "translation_stats": dict(self.engine.stats),
            "structure_integrity": integrity.to_dict(),
            "manual_visual_check_required": True,
            "items": report_items,
            "warnings": (
                [
                    "Tidak ada text element yang berubah pada run ini. "
                    "Periksa preserved/manual_review/unchanged dan document intelligence."
                ]
                if written == 0
                else []
            ),
        }
        report_path = target_path.with_suffix(".phase5165-report.json")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        return report
