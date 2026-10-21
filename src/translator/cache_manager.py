import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class CacheManager:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS translation_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cache_key TEXT UNIQUE,
                source_text TEXT,
                target_text TEXT,
                model TEXT,
                prompt_version TEXT,
                terminology_version TEXT,
                created_at TEXT
            )
            """)

    def get(self, key):
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT target_text FROM translation_cache WHERE cache_key=?",
                (key,),
            ).fetchone()
        return row[0] if row else None

    def save(self, key, value, model=None, prompt_version=None,
             terminology_version=None, source_text=None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            INSERT OR REPLACE INTO translation_cache
            (cache_key,source_text,target_text,model,prompt_version,terminology_version,created_at)
            VALUES (?,?,?,?,?,?,?)
            """, (
                key,
                source_text if source_text is not None else key,
                value,
                model,
                prompt_version,
                terminology_version,
                datetime.now(UTC).isoformat(),
            ))
