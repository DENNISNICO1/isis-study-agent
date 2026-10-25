import pytest

from isis_agent.config import ConfigError, load_config, load_token


def write(tmp_path, text):
    path = tmp_path / "kurse.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_config_reads_courses(tmp_path):
    cfg = load_config(
        write(
            tmp_path,
            '[isis]\nbase_url = "https://isis.tu-berlin.de/"\n'
            '[[kurs]]\nslug = "psychoakustik"\nname = "Psychoakustik"\nid = 42\n',
        )
    )
    assert cfg.base_url == "https://isis.tu-berlin.de"
    assert cfg.kurs("psychoakustik").id == 42
    assert cfg.kurs("psychoakustik").suche == "Psychoakustik"


def test_beispiel_config_ist_gueltig():
    from pathlib import Path

    cfg = load_config(Path(__file__).parents[1] / "config" / "kurse.example.toml")
    assert cfg.slugs() == ["stroemungsakustik", "psychoakustik"]


@pytest.mark.parametrize(
    "text",
    [
        '[isis]\nbase_url = "http://isis.tu-berlin.de"\n',
        '[isis]\nbase_url = "https://x"\n[[kurs]]\nslug = "Strömung"\n',
        '[isis]\nbase_url = "https://x"\n[[kurs]]\nslug = "a"\n[[kurs]]\nslug = "a"\n',
    ],
)
def test_invalid_config(tmp_path, text):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_unknown_course(tmp_path):
    cfg = load_config(write(tmp_path, '[isis]\nbase_url = "https://x"\n'))
    with pytest.raises(ConfigError):
        cfg.kurs("fehlt")


def test_token_from_env_is_masked(monkeypatch):
    monkeypatch.setenv("ISIS_TOKEN", "abc123")
    token = load_token()
    assert token.reveal() == "abc123"
    assert "abc123" not in repr(token) and "abc123" not in str(token)


def test_token_from_dotenv(monkeypatch, tmp_path):
    monkeypatch.delenv("ISIS_TOKEN", raising=False)
    env = tmp_path / ".env"
    env.write_text("# Kommentar\nISIS_TOKEN='xyz'\n", encoding="utf-8")
    assert load_token(env).reveal() == "xyz"


def test_missing_token(monkeypatch, tmp_path):
    monkeypatch.delenv("ISIS_TOKEN", raising=False)
    with pytest.raises(ConfigError, match="ISIS_TOKEN"):
        load_token(tmp_path / ".env")


def test_podcast_defaults_und_werte(tmp_path):
    base = '[isis]\nbase_url = "https://x"\n'
    assert load_config(write(tmp_path, base)).podcast.backend == "edge"
    cfg = load_config(
        write(
            tmp_path,
            base + '[podcast]\ntempo = "+10%"\nsite_url = "https://p.example.workers.dev"\n',
        )
    )
    assert (cfg.podcast.tempo, cfg.podcast.site_url) == ("+10%", "https://p.example.workers.dev")


@pytest.mark.parametrize(
    "podcast, meldung",
    [
        ('tempo = "schnell"', "tempo"),
        ('site_url = "http://p.dev"', "site_url"),
        ('cloudflare_projekt = "Mein Projekt"', "cloudflare_projekt"),
    ],
)
def test_podcast_ungueltig(tmp_path, podcast, meldung):
    with pytest.raises(ConfigError, match=meldung):
        load_config(write(tmp_path, f'[isis]\nbase_url = "https://x"\n[podcast]\n{podcast}\n'))


def test_env_value(monkeypatch, tmp_path):
    from isis_agent.config import env_value

    monkeypatch.delenv("PODCAST_SECRET", raising=False)
    dotenv = tmp_path / ".env"
    assert env_value("PODCAST_SECRET", dotenv) == ""
    dotenv.write_text("PODCAST_SECRET='abc'\n", encoding="utf-8")
    assert env_value("PODCAST_SECRET", dotenv) == "abc"
    monkeypatch.setenv("PODCAST_SECRET", "env")
    assert env_value("PODCAST_SECRET", dotenv) == "env"
