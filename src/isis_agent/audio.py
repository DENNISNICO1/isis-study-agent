"""Hörskript → MP3-Folge mit Pausen und Kapitelmarken (Montage als WAV, Kodierung per ffmpeg)."""

import logging
import os
import re
import shutil
import subprocess
import tempfile
import wave
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from .hoerskript import Hoerskript, Pause, Sprechtext
from .tts import TTSBackend

log = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
SAMPLE_BYTES = 2
BITRATE = "64k"
PAUSE_NACH_TITEL = 0.6
PAUSE_NACH_KAPITEL = 1.0
MAX_FOLGE_BYTES = 25 * 1024 * 1024  # Dateilimit von Cloudflare Static Assets
PARALLEL = 4  # gleichzeitige TTS-Anfragen (edge-tts braucht mehrere Sekunden pro Anfrage)


class AudioError(RuntimeError):
    """Audio konnte nicht erzeugt werden."""


@dataclass(frozen=True)
class KapitelMarke:
    titel: str
    start_ms: int
    ende_ms: int


@dataclass(frozen=True)
class Folge:
    datei: Path
    dauer_s: float
    groesse: int
    kapitel: tuple[KapitelMarke, ...]


class Ffmpeg:
    """Dünne Hülle um das ffmpeg-Binary (austauschbar für Tests)."""

    def __init__(
        self,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        binary: str | None = None,
    ) -> None:
        self.runner = runner
        self.binary = binary

    def _run(self, *args: str) -> None:
        binary = self.binary or shutil.which("ffmpeg")
        if not binary:
            raise AudioError("ffmpeg nicht gefunden – installieren mit `brew install ffmpeg`")
        try:
            self.runner(
                [binary, "-y", "-loglevel", "error", *args],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise AudioError(f"ffmpeg fehlgeschlagen: {(exc.stderr or '').strip()[-500:]}") from exc

    def to_wav(self, quelle: Path, ziel: Path) -> None:
        self._run(
            "-i", str(quelle), "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", str(ziel)
        )

    def encode_mp3(self, wav: Path, metadaten: Path, ziel: Path) -> None:
        self._run(
            "-i", str(wav),
            "-f", "ffmetadata", "-i", str(metadaten),
            "-map", "0:a", "-map_metadata", "1", "-map_chapters", "1",
            "-c:a", "libmp3lame", "-b:a", BITRATE, "-ac", "1",
            "-id3v2_version", "3", "-f", "mp3", str(ziel),
        )  # fmt: skip


def _escape(wert: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", wert)


def ffmetadata(titel: str, album: str, autor: str, kapitel: list[KapitelMarke]) -> str:
    """ID3-Tags und Kapitel im ffmetadata-Format."""
    zeilen = [
        ";FFMETADATA1",
        f"title={_escape(titel)}",
        f"album={_escape(album)}",
        f"artist={_escape(autor)}",
        "genre=Podcast",
    ]
    for k in kapitel:
        zeilen += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={k.start_ms}",
            f"END={k.ende_ms}",
            f"title={_escape(k.titel)}",
        ]
    return "\n".join(zeilen) + "\n"


def _sprechtexte(skript: Hoerskript) -> list[str]:
    """Alle gesprochenen Texte in der Reihenfolge, in der render_folge sie abspielt."""
    texte = [skript.titel]
    for kapitel in skript.kapitel:
        texte.append(kapitel.titel)
        texte += [s.text for s in kapitel.segmente if isinstance(s, Sprechtext)]
    return texte


def _synthetisiere(
    texte: list[str], backend: TTSBackend, ffmpeg: Ffmpeg, tmp: Path, parallel: int
) -> list[Path]:
    """Vertont alle Texte parallel; Ergebnis in Eingabereihenfolge als WAV-Pfade."""

    def eins(nr: int, text: str) -> Path:
        roh = tmp / f"{nr:04d}-roh{backend.suffix}"
        wav = tmp / f"{nr:04d}.wav"
        backend.synthesize(text, roh)
        ffmpeg.to_wav(roh, wav)
        return wav

    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        return list(pool.map(eins, range(1, len(texte) + 1), texte))


class _Montage:
    """Hängt vorab vertonte Sprachabschnitte und Stille an eine Mono-WAV-Datei an."""

    def __init__(self, out: wave.Wave_write, wavs: Iterator[Path]):
        self.out, self.wavs = out, wavs
        self.frames = 0

    @property
    def ms(self) -> int:
        return round(self.frames * 1000 / SAMPLE_RATE)

    def stille(self, sekunden: float) -> None:
        n = round(sekunden * SAMPLE_RATE)
        self.out.writeframes(b"\x00" * (n * SAMPLE_BYTES))
        self.frames += n

    def sprich(self) -> None:
        wav = next(self.wavs)
        with wave.open(str(wav), "rb") as teil:
            params = (teil.getnchannels(), teil.getsampwidth(), teil.getframerate())
            if params != (1, SAMPLE_BYTES, SAMPLE_RATE):
                raise AudioError(f"Unerwartetes Audioformat {params} in {wav.name}")
            n = teil.getnframes()
            self.out.writeframes(teil.readframes(n))
        self.frames += n


def render_folge(
    skript: Hoerskript,
    backend: TTSBackend,
    ziel: Path,
    ffmpeg: Ffmpeg,
    album: str,
    autor: str,
    parallel: int = PARALLEL,
) -> Folge:
    """Spricht alle Kapitel (Titel + Segmente), fügt Pausen ein und schreibt `ziel` atomar."""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="isis-audio-") as tmpdir:
        tmp = Path(tmpdir)
        wavs = _synthetisiere(_sprechtexte(skript), backend, ffmpeg, tmp, parallel)
        voll = tmp / "folge.wav"
        marken: list[KapitelMarke] = []
        with wave.open(str(voll), "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(SAMPLE_BYTES)
            out.setframerate(SAMPLE_RATE)
            m = _Montage(out, iter(wavs))
            for i, kapitel in enumerate(skript.kapitel):
                start = m.ms
                if i == 0:
                    m.sprich()  # Folgentitel
                    m.stille(PAUSE_NACH_TITEL)
                m.sprich()  # Kapiteltitel
                m.stille(PAUSE_NACH_TITEL)
                for segment in kapitel.segmente:
                    if isinstance(segment, Pause):
                        m.stille(segment.sekunden)
                    else:
                        m.sprich()
                m.stille(PAUSE_NACH_KAPITEL)
                marken.append(KapitelMarke(kapitel.titel, start, m.ms))
            dauer = m.frames / SAMPLE_RATE
        meta = tmp / "metadaten.txt"
        meta.write_text(ffmetadata(skript.titel, album, autor, marken), encoding="utf-8")
        teilziel = ziel.with_name(f".{ziel.stem}.tmp.mp3")
        ffmpeg.encode_mp3(voll, meta, teilziel)
        os.replace(teilziel, ziel)
    groesse = ziel.stat().st_size
    if groesse > MAX_FOLGE_BYTES:
        log.warning("%s ist %.1f MB groß (> 25 MB Limit von Cloudflare)", ziel, groesse / 1e6)
    return Folge(ziel, dauer, groesse, tuple(marken))
