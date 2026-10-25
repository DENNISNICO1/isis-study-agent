"""Sichere Datei- und Verzeichnisnamen aus ISIS-Daten."""

import re
import unicodedata
from pathlib import Path, PurePosixPath

_UMLAUTE = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"}
)
_UNSAFE = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
MAX_NAME = 120


def slugify(text: str, max_len: int = 60) -> str:
    """ASCII-Slug für Verzeichnisnamen, z. B. 'Woche 3: Schall' -> 'woche-3-schall'."""
    text = unicodedata.normalize("NFKD", text.translate(_UMLAUTE))
    text = text.encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:max_len].rstrip("-") or "unbenannt"


def safe_name(name: str) -> str:
    """Einzelner Dateiname ohne Pfadtrenner, Steuerzeichen oder führende Punkte."""
    name = _UNSAFE.sub("_", unicodedata.normalize("NFC", name)).strip().lstrip(".")
    if len(name) > MAX_NAME:
        stem, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 10:
            name = stem[: MAX_NAME - len(ext) - 1] + "." + ext
        else:
            name = name[:MAX_NAME]
    return name or "_"


def safe_relpath(moodle_path: str) -> Path:
    """Moodle-'filepath' (z. B. '/Unterordner/') in einen sicheren relativen Pfad umwandeln."""
    parts = [p for p in PurePosixPath(moodle_path or "/").parts if p not in ("/", "", ".", "..")]
    return Path(*[safe_name(p) for p in parts]) if parts else Path()


def ensure_within(root: Path, target: Path) -> Path:
    resolved = target.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"Pfad verlässt das Datenverzeichnis: {target}")
    return target
