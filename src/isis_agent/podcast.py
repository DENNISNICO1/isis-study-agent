"""Privater Lernpodcast: Episodenkatalog, statische Site mit RSS-Feed pro Kurs, Upload."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.utils import format_datetime
from importlib import resources
from pathlib import Path
from urllib.parse import quote

KATALOG_VERSION = 1
AUDIO_VERSION = "1"  # erhöhen, wenn sich das Rendering ändert → alle Folgen neu
ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,}$")
WRANGLER = "wrangler@4"
COMPATIBILITY_DATE = "2026-10-01"
ET.register_namespace("itunes", ITUNES)


class PodcastError(ValueError):
    """Feed kann nicht gebaut werden."""


@dataclass
class Episode:
    key: str  # "<kurs>/<skriptname>"
    kurs: str
    titel: str
    datei: str  # relativ zum Ausgabeverzeichnis
    groesse: int
    dauer_s: float
    hash: str
    veroeffentlicht: str  # ISO-8601
    beschreibung: str = ""

    @property
    def guid(self) -> str:
        return f"{self.key}#{self.hash[:12]}"


@dataclass
class Katalog:
    path: Path
    episoden: dict[str, Episode] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "Katalog":
        if not path.is_file():
            return cls(path=path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(path=path, episoden={k: Episode(**v) for k, v in data["episoden"].items()})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": KATALOG_VERSION,
            "episoden": {k: asdict(e) for k, e in sorted(self.episoden.items())},
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    def braucht_render(self, key: str, hash_: str, out_dir: Path) -> bool:
        ep = self.episoden.get(key)
        return ep is None or ep.hash != hash_ or not (out_dir / ep.datei).is_file()

    def fuer_kurs(self, slug: str) -> list[Episode]:
        eps = [e for e in self.episoden.values() if e.kurs == slug]
        return sorted(eps, key=lambda e: (e.veroeffentlicht, e.key))


def skript_hash(text: str, backend: str, stimme: str, tempo: str) -> str:
    """Ändert sich, sobald Skript, Stimme oder Rendering anders sind."""
    h = hashlib.sha256()
    for teil in (AUDIO_VERSION, backend, stimme, tempo, text):
        h.update(teil.encode("utf-8") + b"\x00")
    return h.hexdigest()


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    el = ET.SubElement(parent, tag, attrs)
    if text is not None:
        el.text = text
    return el


def render_feed(
    titel: str, autor: str, episoden: list[Episode], base_url: str, now: datetime
) -> str:
    """RSS 2.0 mit iTunes-Tags, neueste Folge zuerst; `itunes:block` hält ihn aus Verzeichnissen."""
    rss = ET.Element("rss", {"version": "2.0"})
    ch = _sub(rss, "channel")
    _sub(ch, "title", titel)
    _sub(ch, "link", base_url)
    _sub(ch, "description", f"{titel}: vertonte Lernunterlagen (privat, nicht weitergeben).")
    _sub(ch, "language", "de-de")
    _sub(ch, "lastBuildDate", format_datetime(now))
    _sub(ch, f"{{{ITUNES}}}author", autor)
    _sub(ch, f"{{{ITUNES}}}block", "Yes")
    _sub(ch, f"{{{ITUNES}}}explicit", "false")
    _sub(ch, f"{{{ITUNES}}}type", "episodic")
    _sub(ch, f"{{{ITUNES}}}category", text="Education")
    for ep in reversed(episoden):
        item = _sub(ch, "item")
        _sub(item, "title", ep.titel)
        _sub(item, "description", ep.beschreibung)
        _sub(item, "guid", ep.guid, isPermaLink="false")
        _sub(item, "pubDate", format_datetime(datetime.fromisoformat(ep.veroeffentlicht)))
        url = f"{base_url}/{quote(Path(ep.datei).name)}"
        _sub(item, "enclosure", url=url, length=str(ep.groesse), type="audio/mpeg")
        _sub(item, f"{{{ITUNES}}}duration", str(round(ep.dauer_s)))
        _sub(item, f"{{{ITUNES}}}episodeType", "full")
    ET.indent(rss)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode") + "\n"


def _verlinke(quelle: Path, ziel: Path) -> None:
    try:
        os.link(quelle, ziel)
    except OSError:
        shutil.copy2(quelle, ziel)


def basis_site(out_dir: Path) -> Path:
    """Leert `out_dir/site` und legt 404-Seite, robots.txt und noindex-Header an."""
    site = out_dir / "site"
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / "404.html").write_text("Nicht gefunden\n", encoding="utf-8")
    (site / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (site / "_headers").write_text(
        "/*\n  X-Robots-Tag: noindex, nofollow\n/*/feed.xml\n"
        "  Content-Type: application/rss+xml; charset=utf-8\n",
        encoding="utf-8",
    )
    return site


def baue_site(
    out_dir: Path,
    katalog: Katalog,
    kurse: list[tuple[str, str]],
    secret: str,
    site_url: str,
    autor: str,
    now: datetime,
) -> dict[str, str]:
    """Baut `out_dir/site/<secret>/<kurs>/` (MP3s + feed.xml) neu; gibt Feed-URL je Kurs zurück."""
    if not SECRET_RE.match(secret):
        raise PodcastError("PODCAST_SECRET muss ≥ 16 Zeichen aus A-Z, a-z, 0-9, _ und - sein")
    site = basis_site(out_dir)
    feeds: dict[str, str] = {}
    for slug, name in kurse:
        episoden = katalog.fuer_kurs(slug)
        if not episoden:
            continue
        kurs_dir = site / secret / slug
        kurs_dir.mkdir(parents=True)
        for ep in episoden:
            _verlinke(out_dir / ep.datei, kurs_dir / Path(ep.datei).name)
        base_url = f"{site_url.rstrip('/')}/{secret}/{slug}"
        feed = render_feed(f"{name} – Lernpodcast", autor, episoden, base_url, now)
        (kurs_dir / "feed.xml").write_text(feed, encoding="utf-8")
        feeds[slug] = f"{base_url}/feed.xml"
    return feeds


def deploy_cloudflare(
    site: Path,
    projekt: str,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Lädt die Site als Cloudflare Worker mit Static Assets hoch (Pages ist darin aufgegangen).

    Ein kleiner Worker (cloudflare_worker.js) liegt davor, weil Static Assets keine Range-Anfragen
    beantworten, die der iOS-Player zum Streamen braucht.

    Die Konfiguration liegt neben der Site; Vorschau-URLs sind aus, damit alte Versionen
    (mit evtl. altem Secret im Pfad) nicht unter eigener Adresse erreichbar bleiben.
    """
    if shutil.which("npx") is None:
        raise PodcastError("npx (Node.js) fehlt – installieren mit `brew install node`")
    worker = site.parent / "worker.js"
    worker.write_text(
        resources.files(__package__).joinpath("cloudflare_worker.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    config = site.parent / "wrangler.jsonc"
    config.write_text(
        json.dumps(
            {
                "name": projekt,
                "main": f"./{worker.name}",
                "compatibility_date": COMPATIBILITY_DATE,
                "workers_dev": True,
                "preview_urls": False,
                "assets": {
                    "directory": f"./{site.name}",
                    "binding": "ASSETS",
                    "run_worker_first": True,  # Worker ergänzt Range-Anfragen
                    "not_found_handling": "404-page",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # wrangler cacht die Konto-ID im Arbeitsordner; nach Kontowechsel gibt das Auth-Fehler.
    (site.parent / ".wrangler" / "cache" / "wrangler-account.json").unlink(missing_ok=True)
    cmd = ["npx", "--yes", WRANGLER, "deploy", "--config", str(config)]
    try:
        runner(cmd, check=True, cwd=site.parent)
    except subprocess.CalledProcessError as exc:
        raise PodcastError(
            "Upload zu Cloudflare fehlgeschlagen – einmalig `npx wrangler login` ausführen, "
            "dann erneut versuchen (docs/PODCAST.md)"
        ) from exc
