"""Inkrementeller Sync der Kursmaterialien (core_course_get_contents)."""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import Kurs
from .htmltext import html_to_text
from .moodle_client import MoodleClient
from .paths import ensure_within, safe_name, safe_relpath, slugify
from .state import Manifest

log = logging.getLogger(__name__)

FILE_MODULES = {"resource", "folder", "page"}


@dataclass(frozen=True)
class FileChange:
    kind: str  # "neu" | "geändert"
    section: str
    module: str
    path: Path  # relativ zum Kursverzeichnis


@dataclass(frozen=True)
class LinkItem:
    section: str
    name: str
    url: str


@dataclass
class SyncResult:
    changes: list[FileChange] = field(default_factory=list)
    unchanged: int = 0
    links: list[LinkItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    overview: Path | None = None


def sync_material(
    client: MoodleClient, kurs: Kurs, kurs_dir: Path, manifest: Manifest
) -> SyncResult:
    """Lädt neue/geänderte Dateien eines Kurses und schreibt eine Kursübersicht."""
    sections = client.call("core_course_get_contents", courseid=kurs.id)
    result = SyncResult()
    for index, section in enumerate(sections):
        section_name = section.get("name") or f"Abschnitt {index}"
        section_dir = Path("material") / f"{index:02d}-{slugify(section_name)}"
        for module in section.get("modules", []):
            if not module.get("uservisible", True):
                continue
            if module.get("modname") == "url":
                for item in module.get("contents", []):
                    if item.get("type") == "url" and item.get("fileurl"):
                        result.links.append(
                            LinkItem(section_name, module.get("name", ""), item["fileurl"])
                        )
            elif module.get("modname") in FILE_MODULES:
                _sync_module_files(
                    client, module, section_name, section_dir, kurs_dir, manifest, result
                )
    result.overview = write_overview(kurs, sections, kurs_dir)
    return result


def _sync_module_files(
    client: MoodleClient,
    module: dict[str, Any],
    section_name: str,
    section_dir: Path,
    kurs_dir: Path,
    manifest: Manifest,
    result: SyncResult,
) -> None:
    module_name = module.get("name", "")
    files = [c for c in module.get("contents", []) if c.get("type") == "file" and c.get("fileurl")]
    # Ordner, Seiten und Ressourcen mit mehreren Dateien bekommen ein eigenes Unterverzeichnis.
    base = section_dir
    if module.get("modname") != "resource" or len(files) > 1:
        base = section_dir / slugify(module_name)
    for item in files:
        rel = base / safe_relpath(item.get("filepath", "/")) / safe_name(item.get("filename", ""))
        key = f"{module.get('id')}:{item.get('filepath', '/')}{item.get('filename', '')}"
        signature = {"timemodified": item.get("timemodified"), "filesize": item.get("filesize")}
        known = manifest.files.get(key)
        target = ensure_within(kurs_dir, kurs_dir / rel)
        if known and _same(known, signature) and target.is_file():
            result.unchanged += 1
            continue
        try:
            client.download(item["fileurl"], target)
        except Exception as exc:  # einzelne Datei darf den Lauf nicht abbrechen
            result.errors.append(f"{rel}: {exc}")
            log.warning("Download fehlgeschlagen: %s", rel)
            continue
        if known and known.get("path") != str(rel):
            _remove_stale(kurs_dir, known.get("path"))
        manifest.files[key] = {**signature, "path": str(rel), "module": module_name}
        kind = "geändert" if known else "neu"
        result.changes.append(FileChange(kind, section_name, module_name, rel))


def _same(known: dict[str, Any], signature: dict[str, Any]) -> bool:
    return all(known.get(k) == v for k, v in signature.items())


def _remove_stale(kurs_dir: Path, old: str | None) -> None:
    if old:
        (kurs_dir / old).unlink(missing_ok=True)


def write_overview(kurs: Kurs, sections: list[dict[str, Any]], kurs_dir: Path) -> Path:
    """Schreibt uebersicht.md: Abschnitte, Module, Beschreibungen und Links des Kurses."""
    lines = [f"# {kurs.name} – Kursübersicht (aus ISIS)", ""]
    for index, section in enumerate(sections):
        lines.append(f"## {section.get('name') or f'Abschnitt {index}'}")
        summary = html_to_text(section.get("summary"))
        if summary:
            lines += ["", summary]
        lines.append("")
        for module in section.get("modules", []):
            if not module.get("uservisible", True):
                continue
            entry = f"- **{module.get('name', '')}** ({module.get('modname', '')})"
            urls = [c["fileurl"] for c in module.get("contents", []) if c.get("type") == "url"]
            if urls:
                entry += " – " + ", ".join(f"<{u}>" for u in urls)
            lines.append(entry)
            description = html_to_text(module.get("description"))
            if description:
                lines += ["  " + line for line in description.splitlines()]
        lines.append("")
    path = kurs_dir / "uebersicht.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path
