import tomllib

import httpx
import pytest

from isis_agent import cli
from isis_agent.config import Kurs, Secret, load_config, render_config
from isis_agent.moodle_client import MoodleClient

from .conftest import BASE, TOKEN

COURSES = [
    {"id": 101, "fullname": "Strömungsakustik WiSe 2026/27"},
    {"id": 202, "fullname": "Psychoakustik I"},
    {"id": 303, "fullname": "Psychoakustik I"},
]


@pytest.fixture
def root(tmp_path, monkeypatch, fake):
    fake.responses["core_webservice_get_site_info"] = {"userid": 7}
    fake.responses["core_enrol_get_users_courses"] = COURSES

    def neuer_client(base_url, token):
        http = httpx.Client(transport=httpx.MockTransport(fake.handler))
        return MoodleClient(BASE, Secret(TOKEN), http=http, sleep=lambda _s: None)

    monkeypatch.setattr(cli, "MoodleClient", neuer_client)
    monkeypatch.setenv("ISIS_TOKEN", "x")
    return tmp_path


def run(root, *args):
    return cli.main(["--root", str(root), "init", *args])


def test_render_config_roundtrip(tmp_path):
    kurse = [Kurs(slug="sa", name='Kurs "A"', id=1, suche="Kurs")]
    path = tmp_path / "kurse.toml"
    path.write_text(render_config("https://isis.example", kurse), encoding="utf-8")
    cfg = load_config(path)
    assert cfg.base_url == "https://isis.example" and cfg.kurse == kurse
    assert cfg.podcast.stimme == "de-DE-ConradNeural" and cfg.podcast.autor == "ISIS Study Agent"


def test_init_ohne_kurse_listet_nur(root, capsys):
    assert run(root) == 0
    out = capsys.readouterr().out
    assert "id=   101  Strömungsakustik WiSe 2026/27" in out and "--kurs" in out
    assert not (root / "config" / "kurse.toml").exists()


def test_init_schreibt_config_mit_eindeutigen_slugs(root):
    assert run(root, "--kurs", "101", "--kurs", "202", "--kurs", "303") == 0
    cfg = load_config(root / "config" / "kurse.toml")
    assert cfg.slugs() == [
        "stroemungsakustik-wise-2026-27",
        "psychoakustik-i",
        "psychoakustik-i-2",
    ]
    assert cfg.kurs("psychoakustik-i").id == 202
    assert tomllib.loads((root / "config" / "kurse.toml").read_text(encoding="utf-8"))


def test_init_ueberschreibt_nicht_ohne_force(root, capsys):
    assert run(root, "--kurs", "101") == 0
    assert run(root, "--kurs", "202") == 2
    assert "--force" in capsys.readouterr().err
    assert run(root, "--kurs", "202", "--force") == 0
    assert load_config(root / "config" / "kurse.toml").kurse[0].id == 202


def test_init_unbekannte_id(root, capsys):
    assert run(root, "--kurs", "999") == 2
    assert "999" in capsys.readouterr().err


def test_fehlende_config_verweist_auf_init(tmp_path, capsys):
    assert cli.main(["--root", str(tmp_path), "check"]) == 2
    assert "isis-agent init" in capsys.readouterr().err
