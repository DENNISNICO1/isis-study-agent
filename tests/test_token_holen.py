import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "token_holen", Path(__file__).parents[1] / "tools" / "token_holen.py"
)
token_holen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(token_holen)


def redirect(passport, token="tok123", base="https://isis.tu-berlin.de"):
    sig = hashlib.md5((base + passport).encode()).hexdigest()
    raw = base64.b64encode(f"{sig}:::{token}:::priv".encode()).decode()
    return f"moodledownloader://token={raw}"


def test_parse_redirect_extracts_token():
    assert token_holen.parse_redirect(redirect("abc"), "abc") == "tok123"


def test_parse_redirect_rejects_bad_signature():
    with pytest.raises(ValueError, match="Signatur"):
        token_holen.parse_redirect(redirect("abc"), "anders")


def test_parse_redirect_requires_token():
    with pytest.raises(ValueError):
        token_holen.parse_redirect("moodledownloader://nix", "abc")


def test_write_env_replaces_existing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=1\nISIS_TOKEN=alt\n", encoding="utf-8")
    token_holen.write_env("neu", env)
    assert env.read_text(encoding="utf-8") == "FOO=1\nISIS_TOKEN=neu\n"
