import re

import pytest

from isis_agent.hoerskript import (
    HoerskriptError,
    Pause,
    Sprechtext,
    find_skripte,
    load,
    parse,
    split_text,
)

KOPF = "---\ntitel: Test – VL 01\nkurs: psychoakustik\nquelle: woche-x.md\ndatum: 2026-10-24\n---\n"


def skript(body: str) -> str:
    return KOPF + "\n" + body


def test_parse_kapitel_absaetze_und_pausen():
    s = parse(
        skript(
            "## Einstieg\n\nHallo und willkommen.\nZweite Zeile.\n\nNeuer Absatz.\n\n"
            "[PAUSE 2,5s]\n\n## Quiz\n\nFrage eins?\n[PAUSE 8s]\nAntwort."
        )
    )
    assert (s.titel, s.kurs, s.datum) == ("Test – VL 01", "psychoakustik", "2026-10-24")
    assert [k.titel for k in s.kapitel] == ["Einstieg", "Quiz"]
    assert s.kapitel[0].segmente == (
        Sprechtext("Hallo und willkommen. Zweite Zeile."),
        Sprechtext("Neuer Absatz."),
        Pause(2.5),
    )
    assert s.kapitel[1].segmente == (Sprechtext("Frage eins?"), Pause(8.0), Sprechtext("Antwort."))
    assert s.woerter() == 10
    assert s.minuten() == pytest.approx(10 / 110 + (2.5 + 8 + 4.4) / 60)


@pytest.mark.parametrize(
    "body, meldung",
    [
        ("## A\n\nDie Formel $p'$ gilt.", "nicht sprechbare Zeichen $"),
        ("## A\n\nDas ist **fett**.", "*"),
        ("## A\n\n- Punkt eins", "Aufzählung"),
        ("## A\n\n1. Punkt eins", "Aufzählung"),
        ("## A\n\nSiehe [Folie 3](x.md).", "["),
        ("### A\n\nText", "#"),
        ("Text ohne Kapitel", "vor dem ersten"),
        ("## A\n\n[PAUSE 60s]\nText", "Pause muss"),
        ("## A\n\n[PAUSE 2s]", "leer"),
        ("", "keine Kapitel"),
    ],
)
def test_parse_lehnt_unsprechbares_ab(body, meldung):
    with pytest.raises(HoerskriptError, match=re.escape(meldung)):
        parse(skript(body), name="x-hoer.md")


def test_fehlermeldung_hat_zeilennummer():
    with pytest.raises(HoerskriptError, match=r"x-hoer\.md:11:"):
        parse(skript("## A\n\nok\n$x$"), name="x-hoer.md")


@pytest.mark.parametrize(
    "text, meldung",
    [
        ("## A\n\nText", "Kopf mit '---' fehlt"),
        ("---\ntitel: x\n---\n## A\n\nText", "Kopffelder fehlen: kurs, quelle, datum"),
        ("---\ntitel: x\nkurs: k\nquelle: q\ndatum: 24.10.2026\n---\n## A\n\nT", "JJJJ-MM-TT"),
        ("---\ntitel: x\n", "nicht mit '---' beendet"),
        ("---\nkaputt\n---\n", "ohne ':'"),
    ],
)
def test_kopf_fehler(text, meldung):
    with pytest.raises(HoerskriptError, match=meldung):
        parse(text)


def test_split_text_an_satzgrenzen():
    text = "Eins zwei drei. " * 10
    parts = split_text(text.strip(), max_len=40)
    assert all(len(p) <= 40 for p in parts)
    assert " ".join(parts) == text.strip()


def test_split_text_ohne_satzzeichen():
    parts = split_text("wort " * 30, max_len=20)
    assert all(0 < len(p) <= 20 for p in parts)
    assert " ".join(parts).split() == ["wort"] * 30


def test_lange_absaetze_werden_gesplittet():
    s = parse(skript("## A\n\n" + "Ein Satz mit Inhalt. " * 300))
    assert len(s.kapitel[0].segmente) > 1


def test_find_und_load(tmp_path):
    audio = tmp_path / "psychoakustik" / "audio"
    audio.mkdir(parents=True)
    (audio / "b-hoer.md").write_text(skript("## A\n\nText."), encoding="utf-8")
    (audio / "a-hoer.md").write_text(skript("## A\n\nText."), encoding="utf-8")
    (audio / "notiz.md").write_text("x", encoding="utf-8")
    paths = find_skripte(tmp_path, "psychoakustik")
    assert [p.name for p in paths] == ["a-hoer.md", "b-hoer.md"]
    assert load(paths[0]).kapitel[0].titel == "A"
    assert find_skripte(tmp_path, "fehlt") == []
