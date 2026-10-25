import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from isis_agent.podcast import (
    ITUNES,
    Episode,
    Katalog,
    PodcastError,
    baue_site,
    deploy_cloudflare,
    render_feed,
    skript_hash,
)

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
SECRET = "geheim-abcdefghijklmnop"


def episode(stem: str, kurs: str = "psychoakustik", zeit: str = "2026-10-25T12:00:00+00:00"):
    return Episode(
        key=f"{kurs}/{stem}",
        kurs=kurs,
        titel=f"Titel {stem}",
        datei=f"episoden/{kurs}/{stem}.mp3",
        groesse=1234,
        dauer_s=61.4,
        hash="a" * 64,
        veroeffentlicht=zeit,
        beschreibung="Kapitel: Einstieg",
    )


def test_katalog_roundtrip_und_render_entscheidung(tmp_path):
    kat = Katalog.load(tmp_path / ".state" / "episoden.json")
    assert kat.braucht_render("psychoakustik/a", "a" * 64, tmp_path)
    kat.episoden["psychoakustik/a"] = episode("a")
    kat.save()
    kat = Katalog.load(tmp_path / ".state" / "episoden.json")
    assert kat.episoden["psychoakustik/a"].guid == "psychoakustik/a#" + "a" * 12
    assert kat.braucht_render("psychoakustik/a", "a" * 64, tmp_path)  # Datei fehlt
    (tmp_path / "episoden" / "psychoakustik").mkdir(parents=True)
    (tmp_path / "episoden" / "psychoakustik" / "a.mp3").write_bytes(b"x")
    assert not kat.braucht_render("psychoakustik/a", "a" * 64, tmp_path)
    assert kat.braucht_render("psychoakustik/a", "b" * 64, tmp_path)


def test_fuer_kurs_sortiert_nach_zeit():
    kat = Katalog(path=None)  # type: ignore[arg-type]
    kat.episoden = {
        "psychoakustik/b": episode("b", zeit="2026-10-25T12:00:01+00:00"),
        "psychoakustik/a": episode("a", zeit="2026-10-25T12:00:00+00:00"),
        "x/c": episode("c", kurs="x"),
    }
    assert [e.key for e in kat.fuer_kurs("psychoakustik")] == ["psychoakustik/a", "psychoakustik/b"]


def test_skript_hash_haengt_von_stimme_ab():
    a = skript_hash("text", "edge", "Katja", "+0%")
    assert a == skript_hash("text", "edge", "Katja", "+0%")
    assert a != skript_hash("text", "edge", "Conrad", "+0%")
    assert a != skript_hash("text2", "edge", "Katja", "+0%")


def test_render_feed():
    eps = [
        episode("a", zeit="2026-10-25T12:00:00+00:00"),
        episode("b", zeit="2026-10-25T12:00:01+00:00"),
    ]
    xml = render_feed("Psychoakustik – Lernpodcast", "Test Person", eps, "https://x.dev/s/psy", NOW)
    root = ET.fromstring(xml)
    ch = root.find("channel")
    assert ch.findtext("title") == "Psychoakustik – Lernpodcast"
    assert ch.findtext(f"{{{ITUNES}}}block") == "Yes"
    items = ch.findall("item")
    assert [i.findtext("title") for i in items] == ["Titel b", "Titel a"]
    enc = items[0].find("enclosure").attrib
    assert enc == {"url": "https://x.dev/s/psy/b.mp3", "length": "1234", "type": "audio/mpeg"}
    assert items[0].findtext(f"{{{ITUNES}}}duration") == "61"
    assert items[0].findtext("pubDate") == "Sun, 25 Oct 2026 12:00:01 +0000"


def test_baue_site(tmp_path):
    (tmp_path / "episoden" / "psychoakustik").mkdir(parents=True)
    (tmp_path / "episoden" / "psychoakustik" / "a.mp3").write_bytes(b"mp3")
    alt = tmp_path / "site" / "altes-secret"
    alt.mkdir(parents=True)
    kat = Katalog(path=tmp_path / "k.json", episoden={"psychoakustik/a": episode("a")})
    feeds = baue_site(
        tmp_path,
        kat,
        [("psychoakustik", "Psychoakustik"), ("leer", "Leer")],
        SECRET,
        "https://isis.example.workers.dev/",
        "Test Person",
        NOW,
    )
    assert feeds == {
        "psychoakustik": f"https://isis.example.workers.dev/{SECRET}/psychoakustik/feed.xml"
    }
    kurs_dir = tmp_path / "site" / SECRET / "psychoakustik"
    assert (kurs_dir / "a.mp3").read_bytes() == b"mp3"
    assert "a.mp3" in (kurs_dir / "feed.xml").read_text(encoding="utf-8")
    assert not alt.exists()
    assert "noindex" in (tmp_path / "site" / "_headers").read_text(encoding="utf-8")
    assert (tmp_path / "site" / "robots.txt").is_file()


@pytest.mark.parametrize("secret", ["", "kurz", "mit/schraegstrich-abcdefgh", "a b" * 10])
def test_baue_site_prueft_secret(tmp_path, secret):
    with pytest.raises(PodcastError, match="PODCAST_SECRET"):
        baue_site(tmp_path, Katalog(path=tmp_path / "k"), [], secret, "https://x", "N", NOW)


def test_deploy_cloudflare(monkeypatch, tmp_path):
    from isis_agent import podcast

    monkeypatch.setattr(podcast.shutil, "which", lambda _n: "/usr/bin/npx")
    calls = []
    site = tmp_path / "site"
    site.mkdir()
    konto = tmp_path / ".wrangler" / "cache" / "wrangler-account.json"
    konto.parent.mkdir(parents=True)
    konto.write_text("{}", encoding="utf-8")
    deploy_cloudflare(site, "isis-lernpodcast", runner=lambda cmd, **kw: calls.append((cmd, kw)))
    config = tmp_path / "wrangler.jsonc"
    assert calls == [
        (
            ["npx", "--yes", "wrangler@4", "deploy", "--config", str(config)],
            {"check": True, "cwd": tmp_path},
        )
    ]
    assert not konto.exists()
    cfg = json.loads(config.read_text(encoding="utf-8"))
    assert cfg["name"] == "isis-lernpodcast" and cfg["preview_urls"] is False
    assert cfg["main"] == "./worker.js" and cfg["assets"]["binding"] == "ASSETS"
    assert cfg["assets"]["run_worker_first"] is True
    assert "Content-Range" in (tmp_path / "worker.js").read_text(encoding="utf-8")

    def boom(cmd, **kw):
        raise subprocess.CalledProcessError(1, cmd)

    with pytest.raises(PodcastError, match="wrangler login"):
        deploy_cloudflare(site, "p", runner=boom)
    monkeypatch.setattr(podcast.shutil, "which", lambda _n: None)
    with pytest.raises(PodcastError, match="Node.js"):
        deploy_cloudflare(site, "p")
