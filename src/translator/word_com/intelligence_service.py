from __future__ import annotations

import json
from pathlib import Path

from .adapter import WordComAdapter
from .intelligence import WordDocumentAnalyzer
from .walker import WordWalker


class WordIntelligenceService:
    def __init__(self, *, output_dir: str | Path | None = None, adapter=None, walker=None, analyzer=None):
        self.output_dir = Path(output_dir).expanduser().resolve() if output_dir else None
        self.adapter = adapter or WordComAdapter()
        self.walker = walker or WordWalker()
        self.analyzer = analyzer or WordDocumentAnalyzer()

    def analyze(self, source_path: str | None = None, *, domain: str | None = None, style: str | None = None, smart_eligibility: bool = True) -> dict:
        app = self.adapter.attach_application()
        document = self.adapter.get_document(app, source_path)
        source = self.adapter.ensure_saved_source(document)
        stats, elements = self.walker.inspect(document)
        analysis = self.analyzer.analyze(stats, elements, domain=domain, style=style, smart_eligibility=smart_eligibility)
        path = (self.output_dir or source.parent) / f"{source.stem}.phase522-analysis.json"
        payload = {
            "phase": "5.2.2",
            "source_path": str(source),
            "stats": stats.to_dict(),
            "analysis": analysis.to_dict(),
            "elements": [e.to_dict() for e in elements],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["analysis_path"] = str(path)
        return payload
