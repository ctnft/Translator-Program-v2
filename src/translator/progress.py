from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class TranslationProgressStore:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS translation_progress (
                document_id TEXT NOT NULL,
                element_key TEXT NOT NULL,
                source_hash TEXT NOT NULL,
                source_text TEXT NOT NULL,
                target_text TEXT,
                status TEXT NOT NULL,
                origin TEXT,
                error TEXT,
                translation_version TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                PRIMARY KEY(document_id, element_key, source_hash)
            )
            """)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(translation_progress)")}
            if "translation_version" not in columns:
                conn.execute(
                    "ALTER TABLE translation_progress ADD COLUMN translation_version TEXT NOT NULL DEFAULT ''"
                )

    @staticmethod
    def source_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get(self, document_id, element_key, source_text, translation_version=None):
        source_hash = self.source_hash(source_text)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """SELECT target_text,status,origin,error,translation_version FROM translation_progress
                   WHERE document_id=? AND element_key=? AND source_hash=?""",
                (document_id, element_key, source_hash),
            ).fetchone()
        if row is None:
            return None
        if translation_version is not None and str(row[4] or "") != str(translation_version):
            return None
        return {
            "target_text": row[0],
            "status": row[1],
            "origin": row[2],
            "error": row[3],
            "translation_version": row[4],
        }

    def save(
        self,
        document_id,
        element_key,
        source_text,
        target_text,
        status,
        origin,
        error=None,
        translation_version="",
    ):
        source_hash = self.source_hash(source_text)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO translation_progress
                   (document_id,element_key,source_hash,source_text,target_text,status,origin,error,translation_version,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    document_id,
                    element_key,
                    source_hash,
                    source_text,
                    target_text,
                    status,
                    origin,
                    error,
                    translation_version,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def save_many(self, records):
        """Persist multiple progress rows in one SQLite transaction.

        Each record is a mapping accepted by :meth:`save`. This is used by the
        Word adapter to keep checkpoint durability without opening/committing a
        SQLite transaction for every single Word element.
        """
        rows = []
        now = datetime.now(UTC).isoformat()
        for record in records:
            source_text = str(record.get("source_text", ""))
            rows.append((
                str(record["document_id"]),
                str(record["element_key"]),
                self.source_hash(source_text),
                source_text,
                record.get("target_text"),
                str(record["status"]),
                record.get("origin"),
                record.get("error"),
                str(record.get("translation_version", "")),
                now,
            ))
        if not rows:
            return
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO translation_progress
                   (document_id,element_key,source_hash,source_text,target_text,status,origin,error,translation_version,updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )

