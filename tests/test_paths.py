from pathlib import Path

import pytest

from isis_agent.paths import ensure_within, safe_name, safe_relpath, slugify


def test_slugify():
    assert slugify("Woche 3: Strömung & Schall") == "woche-3-stroemung-schall"
    assert slugify("!!!") == "unbenannt"


def test_safe_name_strips_separators_and_dots():
    assert safe_name("../../etc/passwd") == "_.._etc_passwd"
    assert safe_name("") == "_"
    assert "/" not in safe_name("a/b\\c")


def test_safe_name_truncates_keeping_extension():
    name = safe_name("x" * 300 + ".pdf")
    assert len(name) <= 120 and name.endswith(".pdf")


def test_safe_relpath_removes_traversal():
    assert safe_relpath("/Unter/../ordner/") == Path("Unter/ordner")
    assert safe_relpath("/") == Path()


def test_ensure_within(tmp_path):
    assert ensure_within(tmp_path, tmp_path / "a" / "b")
    with pytest.raises(ValueError):
        ensure_within(tmp_path, tmp_path / ".." / "x")
