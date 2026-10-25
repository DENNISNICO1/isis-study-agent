import shutil
import subprocess
import sys
import types
import wave
from pathlib import Path

import pytest

from isis_agent import tts
from isis_agent.audio import (
    SAMPLE_RATE,
    AudioError,
    Ffmpeg,
    KapitelMarke,
    ffmetadata,
    render_folge,
)
from isis_agent.hoerskript import parse

SKRIPT = """---
titel: Test-Folge
kurs: psychoakustik
quelle: woche-x.md
datum: 2026-10-24
---

## Einstieg

Hallo.

[PAUSE 2s]

## Quiz

Frage eins?
"""


def write_wav(path: Path, sekunden: float, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x01\x00" * round(sekunden * rate))


class FakeBackend:
    """Erzeugt pro gesprochenem Text 0,1 s Audio je Wort."""

    name = "fake"
    suffix = ".wav"

    def __init__(self, rate: int = SAMPLE_RATE) -> None:
        self.texte: list[str] = []
        self.rate = rate

    def synthesize(self, text: str, ziel: Path) -> None:
        self.texte.append(text)
        write_wav(ziel, 0.1 * len(text.split()), self.rate)


class FakeFfmpeg(Ffmpeg):
    def __init__(self) -> None:
        super().__init__()
        self.meta = ""

    def to_wav(self, quelle: Path, ziel: Path) -> None:
        shutil.copy(quelle, ziel)

    def encode_mp3(self, wav: Path, metadaten: Path, ziel: Path) -> None:
        self.meta = metadaten.read_text(encoding="utf-8")
        shutil.copy(wav, ziel)


def test_render_folge_reihenfolge_dauer_und_kapitel(tmp_path):
    backend, ffmpeg = FakeBackend(), FakeFfmpeg()
    ziel = tmp_path / "out" / "folge.mp3"
    folge = render_folge(parse(SKRIPT), backend, ziel, ffmpeg, "Psychoakustik", "Test Person")

    assert sorted(backend.texte) == sorted(
        ["Test-Folge", "Einstieg", "Hallo.", "Quiz", "Frage eins?"]
    )
    # Sprache: 6 Wörter à 0,1 s; Stille: 0,6 + 0,6 + 2 + 1 (Kap. 1) + 0,6 + 1 (Kap. 2)
    assert folge.dauer_s == pytest.approx(0.6 + 5.8)
    assert folge.kapitel == (
        KapitelMarke("Einstieg", 0, 4500),
        KapitelMarke("Quiz", 4500, 6400),
    )
    assert ziel.is_file() and folge.groesse == ziel.stat().st_size
    assert not list(ziel.parent.glob(".*.tmp.mp3"))
    assert "title=Test-Folge" in ffmpeg.meta and "START=4500" in ffmpeg.meta


def test_render_folge_lehnt_falsche_abtastrate_ab(tmp_path):
    with pytest.raises(AudioError, match="Audioformat"):
        backend = FakeBackend(rate=16_000)
        render_folge(parse(SKRIPT), backend, tmp_path / "x.mp3", FakeFfmpeg(), "", "")


def test_ffmetadata_escaped_sonderzeichen():
    meta = ffmetadata("A=B; #1", "Kurs", "Ich", [KapitelMarke("x\\y", 0, 10)])
    assert meta.startswith(";FFMETADATA1\n")
    assert "title=A\\=B\\; \\#1" in meta and "title=x\\\\y" in meta


def test_ffmpeg_kommandos():
    calls = []
    ff = Ffmpeg(runner=lambda cmd, **kw: calls.append(cmd), binary="/bin/ffmpeg")
    ff.to_wav(Path("a.mp3"), Path("a.wav"))
    ff.encode_mp3(Path("a.wav"), Path("m.txt"), Path("o.mp3"))
    assert calls[0][:4] == ["/bin/ffmpeg", "-y", "-loglevel", "error"]
    assert calls[0][-1] == "a.wav" and "pcm_s16le" in calls[0]
    assert "-map_chapters" in calls[1] and "libmp3lame" in calls[1] and calls[1][-1] == "o.mp3"


def test_ffmpeg_fehler_werden_zu_audioerror(monkeypatch):
    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd, stderr="kaputt")

    with pytest.raises(AudioError, match="kaputt"):
        Ffmpeg(runner=boom, binary="ffmpeg").to_wav(Path("a"), Path("b"))
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    with pytest.raises(AudioError, match="brew install ffmpeg"):
        Ffmpeg().to_wav(Path("a"), Path("b"))


def fake_edge(monkeypatch, fehler: int) -> list[tuple[str, str, str]]:
    calls: list[tuple[str, str, str]] = []

    class Communicate:
        def __init__(self, text, voice, rate):
            calls.append((text, voice, rate))

        async def save(self, path):
            if len(calls) <= fehler:
                raise ConnectionError("offline")
            Path(path).write_bytes(b"mp3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    return calls


def test_edge_tts_mit_retry(monkeypatch, tmp_path):
    calls = fake_edge(monkeypatch, fehler=1)
    pausen = []
    backend = tts.EdgeTTS(stimme="de-DE-KatjaNeural", tempo="+10%", sleep=pausen.append)
    backend.synthesize("Hallo", tmp_path / "a.mp3")
    assert (tmp_path / "a.mp3").read_bytes() == b"mp3"
    assert calls == [("Hallo", "de-DE-KatjaNeural", "+10%")] * 2 and pausen == [2]


def test_edge_tts_gibt_nach_versuchen_auf(monkeypatch, tmp_path):
    fake_edge(monkeypatch, fehler=99)
    with pytest.raises(tts.TTSError, match="--backend say"):
        tts.EdgeTTS(sleep=lambda _s: None).synthesize("Hallo", tmp_path / "a.mp3")


def test_mac_say(monkeypatch, tmp_path):
    monkeypatch.setattr(tts.shutil, "which", lambda _n: "/usr/bin/say")
    calls = []
    tts.MacSay(stimme="Anna", runner=lambda cmd, **kw: calls.append(cmd)).synthesize(
        "-Text mit Strich", tmp_path / "a.aiff"
    )
    txt, aiff = str(tmp_path / "a.txt"), str(tmp_path / "a.aiff")
    assert calls == [["say", "-v", "Anna", "-f", txt, "-o", aiff]]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "-Text mit Strich"


def test_mac_say_fehler(monkeypatch, tmp_path):
    monkeypatch.setattr(tts.shutil, "which", lambda _n: None)
    with pytest.raises(tts.TTSError, match="nur unter macOS"):
        tts.MacSay().synthesize("x", tmp_path / "a.aiff")


def test_get_backend():
    assert isinstance(tts.get_backend("edge"), tts.EdgeTTS)
    assert tts.get_backend("edge").stimme == tts.DEFAULT_STIMMEN["edge"]
    assert tts.get_backend("say", "Petra").stimme == "Petra"
    with pytest.raises(tts.TTSError, match="Unbekanntes"):
        tts.get_backend("piper")
    with pytest.raises(tts.TTSError, match="englisch"):
        tts.get_backend("edge", "de-DE-SeraphinaMultilingualNeural")


def test_render_folge_haelt_reihenfolge_trotz_paralleler_synthese(tmp_path):
    """Langsame frühe Abschnitte dürfen die Reihenfolge in der Montage nicht ändern."""
    import time

    class Langsam(FakeBackend):
        def synthesize(self, text, ziel):
            time.sleep(0.05 if text == "Test-Folge" else 0)
            write_wav(ziel, 0.1 * len(text.split()) if text != "Hallo." else 1.0)

    ziel = tmp_path / "f.mp3"
    folge = render_folge(parse(SKRIPT), Langsam(), ziel, FakeFfmpeg(), "", "", parallel=4)
    with wave.open(str(ziel), "rb") as w:
        assert w.getnframes() == round(folge.dauer_s * SAMPLE_RATE)
    # "Hallo." (1 s) liegt in Kapitel 1: Titel 0,1 + 0,6 + Kapitel 0,1 + 0,6 + 1 + 2 + 1 s
    assert folge.kapitel[0].ende_ms == 5400


def test_edge_tts_bricht_haengende_anfrage_ab(monkeypatch, tmp_path):
    import asyncio

    calls = []

    class Communicate:
        def __init__(self, text, voice, rate):
            calls.append(text)

        async def save(self, path):
            if len(calls) == 1:
                await asyncio.sleep(10)  # hängt
            Path(path).write_bytes(b"mp3")

    monkeypatch.setitem(sys.modules, "edge_tts", types.SimpleNamespace(Communicate=Communicate))
    tts.EdgeTTS(timeout=0.05, sleep=lambda _s: None).synthesize("Hallo", tmp_path / "a.mp3")
    assert len(calls) == 2 and (tmp_path / "a.mp3").read_bytes() == b"mp3"
