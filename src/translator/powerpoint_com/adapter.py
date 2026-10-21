from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from .errors import (
    NoActivePresentationError,
    PowerPointNotRunningError,
    UnsupportedPlatformError,
    UnsavedPresentationError,
    UnsafeOutputPathError,
)


class PowerPointComAdapter:
    """Attach to Microsoft PowerPoint Desktop using pywin32 late binding."""

    def __init__(self) -> None:
        self._pythoncom = None
        self._win32com = None

    def attach_application(self) -> Any:
        if sys.platform != "win32":
            raise UnsupportedPlatformError("PowerPoint COM hanya tersedia di Windows.")

        try:
            import pythoncom
            import pywintypes
            import win32com.client
        except ImportError as exc:
            raise PowerPointNotRunningError(
                "pywin32 belum terpasang. Jalankan: pip install pywin32"
            ) from exc

        self._pythoncom = pythoncom
        self._win32com = win32com.client
        pythoncom.CoInitialize()
        try:
            return win32com.client.GetActiveObject("PowerPoint.Application")
        except (pywintypes.com_error, Exception) as exc:
            raise PowerPointNotRunningError(
                "Microsoft PowerPoint tidak terdeteksi. Buka PowerPoint terlebih dahulu."
            ) from exc

    def attach(self) -> Any:
        app = self.attach_application()
        try:
            presentation = app.ActivePresentation
        except Exception as exc:
            raise NoActivePresentationError(
                "PowerPoint terdeteksi tetapi tidak ada ActivePresentation."
            ) from exc
        if presentation is None:
            raise NoActivePresentationError(
                "PowerPoint terdeteksi tetapi tidak ada ActivePresentation."
            )
        return app, presentation

    def get_presentation(self, app: Any, source_path: str | os.PathLike[str] | None = None) -> Any:
        if source_path is None:
            try:
                presentation = app.ActivePresentation
            except Exception as exc:
                raise NoActivePresentationError("Tidak ada ActivePresentation.") from exc
            if presentation is None:
                raise NoActivePresentationError("Tidak ada ActivePresentation.")
            return presentation

        target = Path(source_path).expanduser().resolve()
        presentations = app.Presentations
        count = int(getattr(presentations, "Count", 0) or 0)
        for index in range(1, count + 1):
            item = presentations.Item(index)
            try:
                if Path(str(item.FullName)).resolve() == target:
                    return item
            except Exception:
                continue
        if not target.exists():
            raise FileNotFoundError(f"Source PPTX tidak ditemukan: {target}")
        return app.Presentations.Open(str(target), 0, 0, -1)

    @staticmethod
    def ensure_saved_source(presentation: Any) -> Path:
        source_path = str(getattr(presentation, "FullName", "") or "").strip()
        source_dir = str(getattr(presentation, "Path", "") or "").strip()

        if not source_path or not source_dir:
            raise UnsavedPresentationError(
                "Presentasi aktif belum disimpan ke disk. Save PPTX terlebih dahulu."
            )

        return Path(source_path).resolve()

    @staticmethod
    def default_output_path(source_path: Path) -> Path:
        return source_path.with_name(f"{source_path.stem}_PHASE513_POC{source_path.suffix}")

    def create_working_copy(
        self,
        app: Any,
        presentation: Any,
        output_path: str | os.PathLike[str] | None = None,
    ) -> tuple[Any, Path]:
        source_path = self.ensure_saved_source(presentation)
        target = (
            Path(output_path).expanduser().resolve()
            if output_path
            else self.default_output_path(source_path)
        )

        if target == source_path:
            raise UnsafeOutputPathError(
                "Output tidak boleh sama dengan source presentation."
            )

        if target.suffix.lower() != source_path.suffix.lower():
            raise UnsafeOutputPathError(
                "Phase 5.1.3 mengharuskan ekstensi output sama dengan source agar format file tidak mismatch."
            )

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            target.unlink()

        # SaveCopyAs explicitly saves a copy without modifying the original.
        presentation.SaveCopyAs(str(target))

        # Presentations.Open(FileName, ReadOnly, Untitled, WithWindow)
        copy_presentation = app.Presentations.Open(str(target), 0, 0, -1)
        return copy_presentation, target


    @staticmethod
    def default_translation_output_path(source_path: Path) -> Path:
        return source_path.with_name(f"{source_path.stem}_ID_PHASE514{source_path.suffix}")

    def open_or_create_translation_copy(
        self,
        app: Any,
        presentation: Any,
        output_path: str | os.PathLike[str] | None = None,
        *,
        resume: bool = False,
    ) -> tuple[Any, Path]:
        source_path = self.ensure_saved_source(presentation)
        target = (
            Path(output_path).expanduser().resolve()
            if output_path
            else self.default_translation_output_path(source_path)
        )
        if target == source_path:
            raise UnsafeOutputPathError("Output tidak boleh sama dengan source presentation.")
        if target.suffix.lower() != source_path.suffix.lower():
            raise UnsafeOutputPathError("Ekstensi output harus sama dengan source.")
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() and resume:
            return self.get_presentation(app, target), target
        if target.exists():
            raise UnsafeOutputPathError(
                f"Output sudah ada: {target}. Gunakan --resume atau pilih --output lain."
            )
        presentation.SaveCopyAs(str(target))
        return app.Presentations.Open(str(target), 0, 0, -1), target

    @staticmethod
    def activate_presentation_window(
        presentation: Any,
        slide_index: int | None = None,
    ) -> None:
        """Bring the output presentation to the front and optionally show a slide."""
        try:
            window = presentation.Windows(1)
            window.Activate()

            if slide_index is not None:
                try:
                    window.View.GotoSlide(int(slide_index))
                except Exception:
                    pass
        except Exception:
            # UI focus is a convenience only; translation/save must not fail because
            # PowerPoint cannot foreground the output window.
            pass

    @staticmethod
    def save(presentation: Any) -> None:
        presentation.Save()
