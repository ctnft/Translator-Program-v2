import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class TranslationMemory:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS translation_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_text TEXT NOT NULL,
                target_text TEXT NOT NULL,
                source_language TEXT NOT NULL DEFAULT 'en',
                target_language TEXT NOT NULL DEFAULT 'id',
                domain TEXT NOT NULL DEFAULT 'food_science',
                context_key TEXT NOT NULL DEFAULT '',
                memory_version TEXT NOT NULL DEFAULT '',
                document_id TEXT,
                confidence REAL DEFAULT 0,
                quality_status TEXT NOT NULL DEFAULT 'machine_validated',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(translation_memory)")}
            additions = {
                "source_language": "TEXT NOT NULL DEFAULT 'en'",
                "target_language": "TEXT NOT NULL DEFAULT 'id'",
                "context_key": "TEXT NOT NULL DEFAULT ''",
                "memory_version": "TEXT NOT NULL DEFAULT ''",
                "document_id": "TEXT",
                "quality_status": "TEXT NOT NULL DEFAULT 'machine_validated'",
                "updated_at": "TEXT",
            }
            for name, ddl in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE translation_memory ADD COLUMN {name} {ddl}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tm_lookup_v2 "
                "ON translation_memory(source_text,source_language,target_language,domain,context_key,memory_version)"
            )

    def save(self, source, target, domain="food_science", context_hash=None, confidence=1.0,
             source_language="en", target_language="id", document_id=None,
             quality_status="machine_validated", memory_version=None):
        context_key = context_hash or ""
        version = memory_version or ""
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT id FROM translation_memory
                   WHERE source_text=? AND source_language=? AND target_language=? AND domain=?
                     AND context_key=? AND memory_version=?
                   ORDER BY id DESC LIMIT 1""",
                (source, source_language, target_language, domain, context_key, version),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE translation_memory SET target_text=?,confidence=?,document_id=?,quality_status=?,updated_at=?
                       WHERE id=?""",
                    (target, confidence, document_id, quality_status, now, row[0]),
                )
            else:
                conn.execute(
                    """INSERT INTO translation_memory
                       (source_text,target_text,source_language,target_language,domain,context_key,memory_version,document_id,
                        confidence,quality_status,created_at,updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (source, target, source_language, target_language, domain, context_key, version, document_id,
                     confidence, quality_status, now, now),
                )

    def lookup(self, source, domain="food_science", context_hash=None,
               source_language="en", target_language="id", memory_version=None):
        context_key = context_hash or ""
        version = memory_version or ""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT target_text FROM translation_memory
                   WHERE source_text=? AND source_language=? AND target_language=? AND domain=?
                     AND context_key=? AND memory_version=?
                     AND quality_status IN ('approved','machine_validated')
                   ORDER BY id DESC LIMIT 1""",
                (source, source_language, target_language, domain, context_key, version),
            ).fetchone()
        return row[0] if row else None
