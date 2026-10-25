import argparse

import pytest

from isis_agent import cli
from isis_agent.state import Manifest

from .conftest import fixture
from .test_forums import setup_fake as setup_forums
from .test_sync import setup_fake as setup_material

ARGS = argparse.Namespace(nur_forum=False, nur_material=False)


def test_sync_course_end_to_end(client, fake, kurs, tmp_path):
    setup_material(fake)
    setup_forums(fake)
    digest = cli.sync_course(
        client, kurs, tmp_path, cli.datetime(2026, 10, 24, tzinfo=cli.UTC), ARGS
    )
    text = digest.read_text(encoding="utf-8")
    assert digest.name == "2026-KW43.md"
    assert (
        "Erstsync" in text and "Materialien (2 neu/geändert" in text and "3 neue Beiträge" in text
    )
    manifest = Manifest.load(tmp_path / kurs.slug / ".state" / "manifest.json")
    assert manifest.runs[0]["files_changed"] == 2 and manifest.runs[0]["new_posts"] == 3

    digest = cli.sync_course(
        client, kurs, tmp_path, cli.datetime(2026, 10, 25, tzinfo=cli.UTC), ARGS
    )
    second = digest.read_text(encoding="utf-8").split("## Lauf")[-1]
    assert "0 neu/geändert" in second and "0 neue Beiträge" in second and "Erstsync" not in second


def test_main_reports_missing_token(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ISIS_TOKEN", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "kurse.toml").write_text(
        '[isis]\nbase_url = "https://x"\n', encoding="utf-8"
    )
    assert cli.main(["--root", str(tmp_path), "check"]) == 2
    assert "ISIS_TOKEN" in capsys.readouterr().err


def test_parser_rejects_conflicting_flags():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["sync", "--nur-material", "--nur-forum"])


def test_fixture_loader():
    assert fixture("forums.json")[0]["type"] == "news"
