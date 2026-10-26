from __future__ import annotations

from .adapter import WordComAdapter
from .walker import WordWalker


class WordPocService:
    def __init__(self, *, adapter=None, walker=None):
        self.adapter = adapter or WordComAdapter()
        self.walker = walker or WordWalker()

    def inspect(self, source_path: str | None = None) -> dict:
        app = self.adapter.attach_application()
        doc = self.adapter.get_document(app, source_path)
        source = self.adapter.ensure_saved_source(doc)
        stats, elements = self.walker.inspect(doc)
        return {
            "phase": "5.2",
            "source_path": str(source),
            "stats": stats.to_dict(),
            "elements": [e.to_dict() for e in elements],
        }
