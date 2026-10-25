"""Hörskripte (kurse/<kurs>/audio/*-hoer.md) einlesen und für die Sprachausgabe prüfen."""

import re
from dataclasses import dataclass
from pathlib import Path

PAUSE_RE = re.compile(r"^\[PAUSE (\d+(?:[.,]\d+)?)s\]$")
DATUM_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KOPF_FELDER = ("titel", "kurs", "quelle", "datum")
# Zeichen, die eine Sprachausgabe falsch oder gar nicht vorliest (LaTeX/Markdown-Reste).
VERBOTEN = set("$\\`*_|#<>{}^[]")
LISTE_RE = re.compile(r"^(?:[-+•]\s|\d+\.\s)")
MIN_PAUSE, MAX_PAUSE = 0.5, 30.0
MAX_SEGMENT = 3000


class HoerskriptError(ValueError):
    """Hörskript verletzt das Format; Meldungen enthalten Datei und Zeilennummer."""


@dataclass(frozen=True)
class Pause:
    sekunden: float


@dataclass(frozen=True)
class Sprechtext:
    text: str


Segment = Pause | Sprechtext


@dataclass(frozen=True)
class Kapitel:
    titel: str
    segmente: tuple[Segment, ...]


@dataclass(frozen=True)
class Hoerskript:
    titel: str
    kurs: str
    quelle: str
    datum: str
    kapitel: tuple[Kapitel, ...]

    def woerter(self) -> int:
        return sum(
            len(s.text.split())
            for k in self.kapitel
            for s in k.segmente
            if isinstance(s, Sprechtext)
        )

    def minuten(self) -> float:
        """Geschätzte Laufzeit: ~110 Wörter/min (edge-tts) plus Pausen."""
        pausen = sum(s.sekunden for k in self.kapitel for s in k.segmente if isinstance(s, Pause))
        return self.woerter() / 110 + (pausen + 2.2 * len(self.kapitel)) / 60


def split_text(text: str, max_len: int = MAX_SEGMENT) -> list[str]:
    """Teilt lange Absätze an Satzgrenzen, damit TTS-Anfragen klein bleiben."""
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    current = ""
    for satz in re.split(r"(?<=[.!?])\s+", text):
        while len(satz) > max_len:  # Satz ohne Satzzeichen: hart an Wortgrenze trennen
            cut = satz.rfind(" ", 0, max_len)
            cut = cut if cut > 0 else max_len
            if current:
                parts.append(current)
                current = ""
            parts.append(satz[:cut].strip())
            satz = satz[cut:].strip()
        if current and len(current) + 1 + len(satz) > max_len:
            parts.append(current)
            current = satz
        else:
            current = f"{current} {satz}".strip()
    if current:
        parts.append(current)
    return parts


def _kopf(lines: list[str], name: str) -> tuple[dict[str, str], int]:
    if not lines or lines[0].strip() != "---":
        raise HoerskriptError(f"{name}:1: Kopf mit '---' fehlt")
    kopf: dict[str, str] = {}
    for nr, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            fehlend = [f for f in KOPF_FELDER if not kopf.get(f)]
            if fehlend:
                raise HoerskriptError(f"{name}: Kopffelder fehlen: {', '.join(fehlend)}")
            if not DATUM_RE.match(kopf["datum"]):
                raise HoerskriptError(f"{name}: datum muss JJJJ-MM-TT sein")
            return kopf, nr
        key, sep, value = line.partition(":")
        if not sep:
            raise HoerskriptError(f"{name}:{nr}: Kopfzeile ohne ':'")
        kopf[key.strip()] = value.strip()
    raise HoerskriptError(f"{name}: Kopf wird nicht mit '---' beendet")


def _pruefe_zeile(line: str, ort: str) -> None:
    falsch = sorted({c for c in line if c in VERBOTEN})
    if falsch:
        raise HoerskriptError(f"{ort}: nicht sprechbare Zeichen {' '.join(falsch)}")
    if LISTE_RE.match(line):
        raise HoerskriptError(f"{ort}: Aufzählung – bitte als Fließtext formulieren")


def parse(text: str, name: str = "<hoerskript>") -> Hoerskript:
    """Parst und validiert ein Hörskript. Wirft HoerskriptError beim ersten Formatfehler."""
    lines = text.splitlines()
    kopf, start = _kopf(lines, name)
    kapitel: list[Kapitel] = []
    titel: str | None = None
    segmente: list[Segment] = []
    absatz: list[str] = []

    def absatz_ende() -> None:
        if absatz:
            segmente.extend(Sprechtext(t) for t in split_text(" ".join(absatz)))
            absatz.clear()

    def kapitel_ende() -> None:
        absatz_ende()
        if titel is not None:
            if not any(isinstance(s, Sprechtext) for s in segmente):
                raise HoerskriptError(f"{name}: Kapitel '{titel}' ist leer")
            kapitel.append(Kapitel(titel, tuple(segmente)))
        segmente.clear()

    for nr, raw in enumerate(lines[start:], start=start + 1):
        line = raw.strip()
        ort = f"{name}:{nr}"
        if line.startswith("## "):
            kapitel_ende()
            titel = line[3:].strip()
            _pruefe_zeile(titel, ort)
            continue
        if not line:
            absatz_ende()
            continue
        if titel is None:
            raise HoerskriptError(f"{ort}: Text vor dem ersten '## Kapitel'")
        if pause := PAUSE_RE.match(line):
            absatz_ende()
            sekunden = float(pause.group(1).replace(",", "."))
            if not MIN_PAUSE <= sekunden <= MAX_PAUSE:
                raise HoerskriptError(f"{ort}: Pause muss {MIN_PAUSE}–{MAX_PAUSE} s lang sein")
            segmente.append(Pause(sekunden))
            continue
        _pruefe_zeile(line, ort)
        absatz.append(line)
    kapitel_ende()
    if not kapitel:
        raise HoerskriptError(f"{name}: keine Kapitel ('## …') gefunden")
    return Hoerskript(
        titel=kopf["titel"],
        kurs=kopf["kurs"],
        quelle=kopf["quelle"],
        datum=kopf["datum"],
        kapitel=tuple(kapitel),
    )


def load(path: Path) -> Hoerskript:
    return parse(path.read_text(encoding="utf-8"), name=str(path))


def find_skripte(kurse_dir: Path, slug: str) -> list[Path]:
    """Alle Hörskripte eines Kurses, sortiert nach Dateiname (= Kursreihenfolge)."""
    return sorted((kurse_dir / slug / "audio").glob("*-hoer.md"))
