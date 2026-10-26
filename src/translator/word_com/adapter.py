from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Any

from .errors import (
    NoActiveDocumentError,
    UnsupportedPlatformError,
    UnsafeOutputPathError,
    UnsavedDocumentError,
    WordNotRunningError,
)


class WordComAdapter:
    """Microsoft Word Desktop COM adapter.

    Source is never overwritten. A byte-for-byte filesystem copy is opened as the
    translation target, then all writes are applied only to that copy.
    """

    def __init__(self) -> None:
        self._pythoncom = None

    def attach_application(self) -> Any:
        if sys.platform != "win32":
            raise UnsupportedPlatformError("Word COM hanya tersedia di Windows.")
        try:
            import pythoncom
            import pywintypes
            import win32com.client
        except ImportError as exc:
            raise WordNotRunningError(
                "pywin32 belum terpasang. Jalankan: pip install pywin32"
            ) from exc

        self._pythoncom = pythoncom
        pythoncom.CoInitialize()
        try:
            return win32com.client.GetActiveObject("Word.Application")
        except Exception:
            try:
                app = win32com.client.Dispatch("Word.Application")
                app.Visible = True
                return app
            except (pywintypes.com_error, Exception) as exc:
                raise WordNotRunningError("Microsoft Word tidak dapat dibuka melalui COM.") from exc

    def get_document(self, app: Any, source_path: str | os.PathLike[str] | None = None) -> Any:
        if source_path is None:
            try:
                document = app.ActiveDocument
            except Exception as exc:
                raise NoActiveDocumentError("Tidak ada ActiveDocument di Microsoft Word.") from exc
            if document is None:
                raise NoActiveDocumentError("Tidak ada ActiveDocument di Microsoft Word.")
            return document

        target = Path(source_path).expanduser().resolve()
        if target.suffix.lower() != ".docx":
            raise ValueError("Phase 5.2.x hanya mendukung source .docx.")
        if not target.exists():
            raise FileNotFoundError(f"Source DOCX tidak ditemukan: {target}")

        documents = app.Documents
        count = int(getattr(documents, "Count", 0) or 0)
        for index in range(1, count + 1):
            item = documents.Item(index)
            try:
                if Path(str(item.FullName)).resolve() == target:
                    return item
            except Exception:
                continue
        # Open(FileName, ConfirmConversions, ReadOnly, AddToRecentFiles)
        return app.Documents.Open(str(target), False, True, False)

    @staticmethod
    def ensure_saved_source(document: Any) -> Path:
        full_name = str(getattr(document, "FullName", "") or "").strip()
        path = str(getattr(document, "Path", "") or "").strip()
        if not full_name or not path:
            raise UnsavedDocumentError("Dokumen Word belum disimpan ke disk.")
        source = Path(full_name).resolve()
        if source.suffix.lower() != ".docx":
            raise ValueError("Phase 5.2.x hanya mendukung .docx.")
        return source

    def open_or_create_translation_copy(
        self,
        app: Any,
        document: Any,
        output_path: str | os.PathLike[str],
        *,
        resume: bool = False,
    ) -> tuple[Any, Path]:
        source = self.ensure_saved_source(document)
        target = Path(output_path).expanduser().resolve()
        if target == source:
            raise UnsafeOutputPathError("Output tidak boleh sama dengan source DOCX.")
        if target.suffix.lower() != ".docx":
            raise UnsafeOutputPathError("Output Phase 5.2.x harus .docx.")
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and resume:
            return self.get_document(app, target), target
        if target.exists():
            raise UnsafeOutputPathError(
                f"Output sudah ada: {target}. Gunakan --resume atau pilih output lain."
            )

        # Copy raw DOCX bytes; this leaves the source document untouched and preserves
        # package parts Word COM does not expose directly.
        shutil.copy2(source, target)
        return app.Documents.Open(str(target), False, False, False), target

    @staticmethod
    def save(document: Any) -> None:
        document.Save()

    @staticmethod
    def activate_document_window(document: Any) -> None:
        try:
            document.Activate()
            document.Application.Visible = True
        except Exception:
            pass
