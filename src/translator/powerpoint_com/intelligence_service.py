from __future__ import annotations

import json
from pathlib import Path

from translator.document_intelligence.analyzer import DocumentIntelligenceAnalyzer
from .adapter import PowerPointComAdapter
from .walker import PowerPointWalker


class PowerPointIntelligenceService:
    def __init__(
        self,
        *,
        output_dir: str | Path | None = None,
        adapter: PowerPointComAdapter | None = None,
        walker: PowerPointWalker | None = None,
        analyzer: DocumentIntelligenceAnalyzer | None = None,
    ):
        self.output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
        self.adapter = adapter or PowerPointComAdapter()
        self.walker = walker or PowerPointWalker()
        self.analyzer = analyzer or DocumentIntelligenceAnalyzer()

    def analyze(self, *, source_path: str | None = None) -> dict:
        app = self.adapter.attach_application()
        presentation = self.adapter.get_presentation(app, source_path)
        source_file = self.adapter.ensure_saved_source(presentation)
        stats, elements = self.walker.inspect(presentation)
        analysis = self.analyzer.analyze(stats, elements)

        report = {
            "phase": "5.1.6.11",
            "mode": "document_analysis",
            "source_path": str(source_file),
            "stats": stats.to_dict(),
            "analysis": analysis.to_dict(),
        }
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{source_file.stem}.phase51611-analysis.json"
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(path)
        return report
