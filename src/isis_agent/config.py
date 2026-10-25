"""Konfiguration: Kursauswahl in config/kurse.toml (lesen/erzeugen) und Secrets aus der Umgebung."""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TOKEN_ENV = "ISIS_TOKEN"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TEMPO_RE = re.compile(r"^[+-]\d{1,3}%$")


class ConfigError(Exception):
    """Fehlerhafte oder unvollständige Konfiguration."""


class Secret:
    """Hält einen geheimen Wert, ohne ihn in repr/str preiszugeben."""

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret('***')"

    __str__ = __repr__


@dataclass(frozen=True)
class Kurs:
    slug: str
    name: str
    id: int
    suche: str

    @property
    def hat_id(self) -> bool:
        return self.id > 0


@dataclass(frozen=True)
class PodcastConfig:
    autor: str = "ISIS Study Agent"
    backend: str = "edge"
    stimme: str = ""  # leer = Standardstimme des Backends
    tempo: str = "+0%"
    site_url: str = ""
    cloudflare_projekt: str = "isis-lernpodcast"


@dataclass(frozen=True)
class Config:
    base_url: str
    kurse: list[Kurs] = field(default_factory=list)
    podcast: PodcastConfig = field(default_factory=PodcastConfig)

    def kurs(self, slug: str) -> Kurs:
        for k in self.kurse:
            if k.slug == slug:
                return k
        raise ConfigError(f"Unbekannter Kurs '{slug}'. Bekannt: {', '.join(self.slugs())}")

    def slugs(self) -> list[str]:
        return [k.slug for k in self.kurse]


def load_config(path: Path) -> Config:
    """Liest und validiert die Kurskonfiguration."""
    if not path.is_file():
        raise ConfigError(
            f"Konfigurationsdatei fehlt: {path} – mit `isis-agent init` erzeugen "
            "oder config/kurse.example.toml kopieren"
        )
    with path.open("rb") as f:
        data = tomllib.load(f)

    base_url = str(data.get("isis", {}).get("base_url", "")).rstrip("/")
    if not base_url.startswith("https://"):
        raise ConfigError("isis.base_url muss mit https:// beginnen")

    kurse: list[Kurs] = []
    for i, raw in enumerate(data.get("kurs", [])):
        slug = str(raw.get("slug", ""))
        if not SLUG_RE.match(slug):
            raise ConfigError(f"kurs[{i}].slug '{slug}' ist ungültig (nur a-z, 0-9, _ und -)")
        name = str(raw.get("name", slug))
        kurse.append(
            Kurs(slug=slug, name=name, id=int(raw.get("id", 0)), suche=str(raw.get("suche", name)))
        )
    if len({k.slug for k in kurse}) != len(kurse):
        raise ConfigError("Kurs-Slugs müssen eindeutig sein")
    return Config(base_url=base_url, kurse=kurse, podcast=_podcast(data.get("podcast", {})))


def _podcast(raw: dict) -> PodcastConfig:
    defaults = PodcastConfig()
    cfg = PodcastConfig(
        **{k: str(raw.get(k, getattr(defaults, k))).strip() for k in defaults.__dataclass_fields__}
    )
    if not TEMPO_RE.match(cfg.tempo):
        raise ConfigError("podcast.tempo muss wie '+0%' oder '-10%' aussehen")
    if cfg.site_url and not cfg.site_url.startswith("https://"):
        raise ConfigError("podcast.site_url muss mit https:// beginnen")
    if not SLUG_RE.match(cfg.cloudflare_projekt):
        raise ConfigError("podcast.cloudflare_projekt: nur a-z, 0-9, _ und -")
    return cfg


def _toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # JSON-Strings sind gültige TOML-Basic-Strings


def render_config(base_url: str, kurse: list[Kurs]) -> str:
    """Erzeugt eine kommentierte config/kurse.toml (für `isis-agent init` und das Beispiel)."""
    zeilen = [
        "# Kursauswahl für den ISIS-Sync. Kurs-IDs listet `isis-agent kurse`.",
        "# slug: ASCII-Kurzname für Ordner (kurse/<slug>/), name: Anzeigename, suche: Namensteil",
        "",
        "[isis]",
        f"base_url = {_toml_str(base_url)}",
    ]
    for k in kurse:
        zeilen += [
            "",
            "[[kurs]]",
            f"slug = {_toml_str(k.slug)}",
            f"name = {_toml_str(k.name)}",
            f"id = {k.id}",
            f"suche = {_toml_str(k.suche)}",
        ]
    zeilen += [
        "",
        "# Lernpodcast (isis-agent audio | feed | publish), siehe docs/PODCAST.md.",
        "# Der geheime Pfad steht NICHT hier, sondern als PODCAST_SECRET in .env.",
        "[podcast]",
        '# autor = "Dein Name"',
        'backend = "edge"  # edge (Neural-Stimmen, online) | say (macOS, offline)',
        'stimme = "de-DE-ConradNeural"  # oder de-DE-KatjaNeural / -AmalaNeural / -KillianNeural',
        'tempo = "+0%"  # z. B. "+10%"; die Podcast-App kann zusätzlich beschleunigen',
        'site_url = ""  # nach dem ersten `isis-agent publish` eintragen',
        'cloudflare_projekt = "isis-lernpodcast"',
    ]
    return "\n".join(zeilen) + "\n"


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def env_value(name: str, dotenv: Path | None = None) -> str:
    """Wert aus der Umgebung, sonst aus einer .env-Datei; leer, wenn nirgends gesetzt."""
    value = os.environ.get(name, "").strip()
    if not value and dotenv is not None:
        value = _read_dotenv(dotenv).get(name, "")
    return value


def load_token(dotenv: Path | None = None) -> Secret:
    """Liest den Token aus der Umgebung, sonst aus einer .env-Datei."""
    value = env_value(TOKEN_ENV, dotenv)
    if not value:
        raise ConfigError(
            f"{TOKEN_ENV} ist nicht gesetzt. Anleitung: docs/ISIS_TOKEN.md "
            "(Token nie in den Chat oder ins Repo schreiben)."
        )
    return Secret(value)
