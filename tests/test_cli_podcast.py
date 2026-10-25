import pytest

from isis_agent import cli, podcast

from .test_audio import SKRIPT, FakeBackend, FakeFfmpeg

SECRET = "geheim-abcdefghijklmnop"


@pytest.fixture
def root(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "kurse.toml").write_text(
        '[isis]\nbase_url = "https://x"\n'
        '[[kurs]]\nslug = "psychoakustik"\nname = "Psychoakustik"\n'
        '[podcast]\nsite_url = "https://isis.example.workers.dev"\n',
        encoding="utf-8",
    )
    audio = tmp_path / "kurse" / "psychoakustik" / "audio"
    audio.mkdir(parents=True)
    (audio / "woche-01-hoer.md").write_text(SKRIPT, encoding="utf-8")
    backend = FakeBackend()
    monkeypatch.setattr(cli, "get_backend", lambda *a: backend)
    monkeypatch.setattr(cli, "Ffmpeg", FakeFfmpeg)
    monkeypatch.delenv("PODCAST_SECRET", raising=False)
    return tmp_path


def run(root, *args):
    return cli.main(["--root", str(root), *args])


def test_audio_rendert_einmal_und_ueberspringt_dann(root, capsys):
    assert run(root, "audio") == 0
    mp3 = root / "podcast_out" / "episoden" / "psychoakustik" / "woche-01.mp3"
    assert mp3.is_file()
    katalog = podcast.Katalog.load(root / "podcast_out" / ".state" / "episoden.json")
    ep = katalog.episoden["psychoakustik/woche-01"]
    assert ep.titel == "Test-Folge" and ep.beschreibung == "Kapitel: Einstieg · Quiz"
    assert run(root, "audio") == 0
    assert "unverändert" in capsys.readouterr().out
    assert run(root, "audio", "--neu") == 0
    assert "vertone" in capsys.readouterr().out


def test_audio_pruefen_meldet_fehler(root, capsys):
    bad = root / "kurse" / "psychoakustik" / "audio" / "woche-02-hoer.md"
    bad.write_text(SKRIPT.replace("Hallo.", "Formel $p$."), encoding="utf-8")
    assert run(root, "audio", "--pruefen") == 1
    out = capsys.readouterr()
    assert "woche-01-hoer.md: 2 Kapitel" in out.out and "$" in out.err
    assert not (root / "podcast_out" / "episoden").exists()


def test_audio_prueft_kurs_im_kopf(root, capsys):
    path = root / "kurse" / "psychoakustik" / "audio" / "woche-01-hoer.md"
    path.write_text(SKRIPT.replace("kurs: psychoakustik", "kurs: falsch"), encoding="utf-8")
    assert run(root, "audio") == 1
    assert "≠ Ordner" in capsys.readouterr().err


def test_audio_entfernt_verwaiste_folgen(root, capsys):
    assert run(root, "audio") == 0
    (root / "kurse" / "psychoakustik" / "audio" / "woche-01-hoer.md").unlink()
    assert run(root, "audio") == 0
    assert "Folge entfernt" in capsys.readouterr().out
    assert not (root / "podcast_out" / "episoden" / "psychoakustik" / "woche-01.mp3").exists()


def test_feed_braucht_secret(root, capsys):
    assert run(root, "feed") == 2
    assert "PODCAST_SECRET" in capsys.readouterr().err


def test_feed_und_publish(root, monkeypatch, capsys):
    (root / ".env").write_text(f"PODCAST_SECRET={SECRET}\n", encoding="utf-8")
    assert run(root, "feed") == 1  # noch keine Folgen
    run(root, "audio")
    assert run(root, "feed") == 0
    assert (
        f"https://isis.example.workers.dev/{SECRET}/psychoakustik/feed.xml"
        in capsys.readouterr().out
    )

    calls = []
    monkeypatch.setattr(cli, "deploy_cloudflare", lambda *a: calls.append(a))
    assert run(root, "publish") == 0
    assert calls == [(root / "podcast_out" / "site", "isis-lernpodcast")]


def test_publish_ohne_site_url_laedt_grundgeruest(root, monkeypatch, capsys):
    toml = root / "config" / "kurse.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace('"https://isis.example.workers.dev"', '""'),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(cli, "deploy_cloudflare", lambda *a: calls.append(a))
    assert run(root, "publish") == 1
    site = root / "podcast_out" / "site"
    assert calls == [(site, "isis-lernpodcast")]
    assert sorted(p.name for p in site.iterdir()) == ["404.html", "_headers", "robots.txt"]
    assert "site_url" in capsys.readouterr().out
