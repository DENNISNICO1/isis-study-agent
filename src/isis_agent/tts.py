"""Sprachausgabe-Backends (kostenlos): edge-tts (online) und macOS say (offline)."""

import asyncio
import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

DEFAULT_STIMMEN = {"edge": "de-DE-KatjaNeural", "say": "Anna"}


class TTSError(RuntimeError):
    """Sprachausgabe fehlgeschlagen."""


class TTSBackend(Protocol):
    name: str
    suffix: str

    def synthesize(self, text: str, ziel: Path) -> None: ...


@dataclass
class EdgeTTS:
    """Microsoft-Neural-Stimmen über das Paket edge-tts (kein Key, inoffizielle Schnittstelle)."""

    stimme: str = DEFAULT_STIMMEN["edge"]
    tempo: str = "+0%"
    versuche: int = 4
    timeout: float = 90.0  # pro Anfrage; edge-tts selbst bricht hängende Verbindungen nicht ab
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    name: str = "edge"
    suffix: str = ".mp3"

    def __post_init__(self) -> None:
        # edge-tts sendet fest xml:lang='en-US'; Multilingual-Stimmen sprechen Deutsch dann
        # mit englischer Aussprache. Einsprachige de-DE-Stimmen sind davon nicht betroffen.
        if "Multilingual" in self.stimme:
            raise TTSError(
                f"Stimme {self.stimme} spricht über edge-tts englisch – "
                "bitte eine einsprachige Stimme wie de-DE-KatjaNeural oder de-DE-ConradNeural"
            )

    def synthesize(self, text: str, ziel: Path) -> None:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - Dependency ist in pyproject
            raise TTSError("Paket edge-tts fehlt: pip install -e .") from exc
        letzter: Exception | None = None
        for versuch in range(1, self.versuche + 1):
            try:
                communicate = edge_tts.Communicate(text, self.stimme, rate=self.tempo)
                asyncio.run(asyncio.wait_for(communicate.save(str(ziel)), self.timeout))
                return
            except Exception as exc:  # edge-tts wirft je nach Fehler aiohttp/eigene Typen
                letzter = exc
                log.info("edge-tts Versuch %d/%d fehlgeschlagen: %s", versuch, self.versuche, exc)
                if versuch < self.versuche:
                    self.sleep(2**versuch)
        raise TTSError(
            f"edge-tts nicht erreichbar ({letzter}). Offline-Alternative: --backend say"
        ) from letzter


@dataclass
class MacSay:
    """macOS-Sprachausgabe (`say`), offline. Bessere Qualität mit Premium-Stimme „Anna“."""

    stimme: str = DEFAULT_STIMMEN["say"]
    runner: Callable[..., subprocess.CompletedProcess] = field(default=subprocess.run, repr=False)
    name: str = "say"
    suffix: str = ".aiff"

    def synthesize(self, text: str, ziel: Path) -> None:
        if shutil.which("say") is None:
            raise TTSError("`say` gibt es nur unter macOS – nutze --backend edge")
        eingabe = ziel.with_suffix(".txt")
        eingabe.write_text(text, encoding="utf-8")
        try:
            self.runner(
                ["say", "-v", self.stimme, "-f", str(eingabe), "-o", str(ziel)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise TTSError(f"say fehlgeschlagen: {exc.stderr.strip()}") from exc


BACKENDS: dict[str, type[EdgeTTS] | type[MacSay]] = {"edge": EdgeTTS, "say": MacSay}


def get_backend(name: str, stimme: str | None = None, tempo: str = "+0%") -> TTSBackend:
    """Backend nach Name; ohne Stimme die Standardstimme des Backends."""
    if name not in BACKENDS:
        raise TTSError(f"Unbekanntes TTS-Backend '{name}'. Bekannt: {', '.join(BACKENDS)}")
    stimme = stimme or DEFAULT_STIMMEN[name]
    if name == "edge":
        return EdgeTTS(stimme=stimme, tempo=tempo)
    return MacSay(stimme=stimme)
