"""Textextraktion aus heruntergeladenen Materialien für die Aufbereitung durch Claude."""

import logging
import shutil
from pathlib import Path

from pypdf import PdfReader

from .htmltext import html_to_text

log = logging.getLogger(__name__)

TEXT_SUFFIXES = {".txt", ".md", ".tex", ".csv"}


def text_path(kurs_dir: Path, material_rel: Path) -> Path:
    """material/... -> text/....txt"""
    rel = (
        material_rel.relative_to("material")
        if material_rel.parts[0] == "material"
        else material_rel
    )
    return kurs_dir / "text" / rel.with_name(rel.name + ".txt")


def extract(kurs_dir: Path, material_rel: Path) -> Path | None:
    """Extrahiert Text einer Datei; gibt den Textpfad zurück oder None, wenn nicht unterstützt."""
    source = kurs_dir / material_rel
    suffix = source.suffix.lower()
    target = text_path(kurs_dir, material_rel)
    try:
        if suffix == ".pdf":
            content = pdf_to_text(source)
        elif suffix in (".html", ".htm"):
            content = html_to_text(source.read_text(encoding="utf-8", errors="replace"))
        elif suffix in TEXT_SUFFIXES:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            return target
        else:
            return None
    except Exception as exc:
        log.warning("Text konnte nicht extrahiert werden (%s): %s", material_rel, exc)
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def pdf_to_text(path: Path) -> str:
    reader = PdfReader(path)
    pages = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append(f"[Seite {number}]\n{text}")
    return "\n\n".join(pages) + "\n"
