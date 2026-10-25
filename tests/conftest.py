"""Gemeinsame Test-Helfer: ein simulierter Moodle-Server über httpx.MockTransport."""

import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from pypdf import PdfWriter

from isis_agent.config import Kurs, Secret
from isis_agent.moodle_client import MoodleClient

BASE = "https://isis.tu-berlin.de"
TOKEN = "geheimertoken123"
FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class FakeMoodle:
    """Antwortet auf wsfunctions mit Fixtures und liefert Dateien aus."""

    def __init__(self) -> None:
        self.responses: dict[str, object] = {}
        self.files: dict[str, bytes] = {}
        self.calls: list[tuple[str, dict]] = []
        self.downloads: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = urlsplit(str(request.url))
        if url.path == "/webservice/rest/server.php":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            assert form["wstoken"] == TOKEN
            fn = form["wsfunction"]
            self.calls.append((fn, form))
            response = self.responses[fn]
            if callable(response):
                response = response(form)
            return httpx.Response(200, json=response)
        query = parse_qs(url.query)
        assert query.get("token") == [TOKEN]
        self.downloads.append(url.path)
        return httpx.Response(200, content=self.files[url.path])


@pytest.fixture
def fake() -> FakeMoodle:
    return FakeMoodle()


@pytest.fixture
def client(fake: FakeMoodle) -> MoodleClient:
    http = httpx.Client(transport=httpx.MockTransport(fake.handler))
    return MoodleClient(BASE, Secret(TOKEN), http=http, sleep=lambda _s: None)


@pytest.fixture
def kurs() -> Kurs:
    return Kurs(slug="psychoakustik", name="Psychoakustik", id=4711, suche="Psychoakustik")
