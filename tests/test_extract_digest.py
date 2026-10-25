from datetime import UTC, datetime
from pathlib import Path

from isis_agent.digest import hints, render_digest, week_label, write_digest
from isis_agent.extract import extract, text_path
from isis_agent.forums import ForumResult, NewPost
from isis_agent.sync import FileChange, SyncResult

from .conftest import blank_pdf

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def post(**kw):
    base = dict(
        forum="Fragen",
        is_announcement=False,
        discussion="Folie 12",
        subject="Folie 12",
        author="Tutor B",
        created=1760000000,
        text="Auf Folie 12 ist ein Fehler.",
        thread_file=Path("forum/fragen/600-folie-12.md"),
    )
    return NewPost(**{**base, **kw})


def test_extract_pdf_and_text(tmp_path):
    rel = Path("material/01-woche/a.pdf")
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(blank_pdf())
    out = extract(tmp_path, rel)
    assert out == text_path(tmp_path, rel) == tmp_path / "text/01-woche/a.pdf.txt"
    assert out.read_text(encoding="utf-8").startswith("[Seite 1]")

    note = Path("material/01-woche/n.txt")
    (tmp_path / note).write_text("Notiz", encoding="utf-8")
    assert extract(tmp_path, note).read_text(encoding="utf-8") == "Notiz"


def test_extract_unsupported_or_broken(tmp_path):
    rel = Path("material/x.pptx")
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_bytes(b"x")
    assert extract(tmp_path, rel) is None
    broken = Path("material/kaputt.pdf")
    (tmp_path / broken).write_bytes(b"kein pdf")
    assert extract(tmp_path, broken) is None


def test_week_label():
    assert week_label(NOW) == "2026-KW43"


def test_hints_flag_corrections():
    assert {"fehler", "folie"} <= set(hints(post()))
    assert hints(post(subject="Hallo", text="Danke!")) == []


def test_render_and_write_digest(tmp_path, kurs):
    rel = Path("material/01-woche/a.pdf")
    material = SyncResult(changes=[FileChange("neu", "Woche 1", "VL01", rel)], unchanged=3)
    forums = ForumResult(
        posts=[post(), post(is_announcement=True, subject="Termin", text="VL entfällt")]
    )
    texts = {rel: tmp_path / "text/01-woche/a.pdf.txt"}
    body = render_digest(kurs, tmp_path, material, forums, texts, NOW, first_run=True)

    assert "Erstsync" in body
    assert (
        "**neu** [Woche 1] VL01: `material/01-woche/a.pdf` → Text: `text/01-woche/a.pdf.txt`"
        in body
    )
    assert body.index("📢 Ankündigung") < body.index("💬 Forum")
    assert "⚠️ Prüfen auf Korrektur" in body

    path = write_digest(tmp_path, "2026-KW43", kurs, body)
    write_digest(tmp_path, "2026-KW43", kurs, "## Lauf 2")
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Digest Psychoakustik – 2026-KW43")
    assert content.count("## Lauf") == 2
