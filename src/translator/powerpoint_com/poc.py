from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .adapter import PowerPointComAdapter
from .errors import TextNotFoundError
from .walker import PowerPointWalker


class PowerPointPocService:
    def __init__(
        self,
        adapter: PowerPointComAdapter | None = None,
        walker: PowerPointWalker | None = None,
    ) -> None:
        self.adapter = adapter or PowerPointComAdapter()
        self.walker = walker or PowerPointWalker()

    def inspect_active(self) -> dict[str, Any]:
        app, presentation = self.adapter.attach()
        source_path = self.adapter.ensure_saved_source(presentation)
        stats, elements = self.walker.inspect(presentation)

        return {
            "source_path": str(source_path),
            "stats": stats.to_dict(),
            "sample_text": [item.to_dict() for item in elements[:20]],
        }

    def replace_one_on_copy(
        self,
        find_text: str,
        replace_text: str,
        output_path: str | None = None,
        *,
        match_case: bool = False,
        whole_words: bool = False,
    ) -> dict[str, Any]:
        app, source = self.adapter.attach()
        source_path = self.adapter.ensure_saved_source(source)
        before_stats, _ = self.walker.inspect(source)
        before_structure = self.walker.structure_snapshot(source)

        copy_presentation, target_path = self.adapter.create_working_copy(
            app,
            source,
            output_path,
        )

        result = self.walker.replace_first(
            copy_presentation,
            find_text,
            replace_text,
            match_case=match_case,
            whole_words=whole_words,
        )

        if not result.replaced:
            try:
                copy_presentation.Close()
            finally:
                try:
                    target_path.unlink()
                except OSError:
                    pass
            raise TextNotFoundError(
                f"Teks tidak ditemukan: {find_text!r}. Tidak ada output yang dipertahankan."
            )

        self.adapter.save(copy_presentation)

        # Make it obvious which presentation was modified. The source remains
        # untouched; foreground the output copy and navigate to the changed slide.
        changed_slide = result.element.slide_index if result.element else None
        self.adapter.activate_presentation_window(
            copy_presentation,
            changed_slide,
        )

        after_stats, _ = self.walker.inspect(copy_presentation)
        after_structure = self.walker.structure_snapshot(copy_presentation)
        integrity = self.walker.compare_structure(before_structure, after_structure)
        if before_stats.slide_count != after_stats.slide_count:
            integrity.differences.append(
                f"Slide count changed: {before_stats.slide_count} -> {after_stats.slide_count}"
            )
        if before_stats.group_count != after_stats.group_count:
            integrity.differences.append(
                f"Group count changed: {before_stats.group_count} -> {after_stats.group_count}"
            )
        if before_stats.table_count != after_stats.table_count:
            integrity.differences.append(
                f"Table count changed: {before_stats.table_count} -> {after_stats.table_count}"
            )
        integrity.passed = not integrity.differences

        report = {
            "phase": "5.1.3",
            "source_path": str(source_path),
            "output_path": str(target_path),
            "replacement": result.to_dict(),
            "before_stats": before_stats.to_dict(),
            "after_stats": after_stats.to_dict(),
            "structure_integrity": integrity.to_dict(),
            "manual_visual_check_required": True,
            "note": (
                "Source presentation tidak diubah. Output copy diaktifkan dan diarahkan "
                "ke slide yang berubah agar mudah diperiksa. PoC ini belum menggunakan Ollama."
            ),
        }

        report_path = target_path.with_suffix(".phase513-report.json")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report["report_path"] = str(report_path)
        return report
