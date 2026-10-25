# isis-study-agent

🇩🇪 Deutsch · [🇬🇧 English](README.en.md)

Ein Study-Agent für **ISIS (Moodle der TU Berlin)**, der mit [Claude Code](https://claude.com/claude-code) arbeitet.
Er synchronisiert deine Kurse (Folien, Übungen, Links, Foren, Ankündigungen) und lässt Claude daraus pro Woche
**Lernunterlagen in Lehrform** schreiben, mit markierten Forum-Korrekturen und Fragen für die **mündliche Prüfung**.
Dazu gibt es interaktive **Lernsessions**, auch am Handy, und optional einen privaten **Lernpodcast** fürs iPhone.

> [!IMPORTANT]
> **Dein Repo muss privat bleiben.** Kursmaterialien sind urheberrechtlich geschützt, Forenbeiträge enthalten
> personenbezogene Daten anderer. Nutze **„Use this template“ → Private**, **nicht „Fork“**: Ein Fork eines
> öffentlichen Repos ist selbst öffentlich.

## Was du bekommst

| Befehl | Was passiert |
|---|---|
| `/wochen-update` | ISIS synchronisieren (nur Neues/Geändertes), Lernunterlagen, Prüfungsfragen, Korrekturen und Hörskripte schreiben |
| `/lernsession <kurs>` | Claude prüft dich wie in der mündlichen Prüfung, sokratisch, eine Frage zur Zeit, und protokolliert Schwächen |
| `isis-agent audio` / `publish` | Hörskripte kostenlos vertonen (MP3 mit Kapiteln) und als privaten Podcast-Feed veröffentlichen |

## Voraussetzungen

- Python ≥ 3.12, Git, ein **Claude-Code**-Zugang (Abo; der Agent nutzt keinen eigenen API-Key)
- Ein ISIS-Konto der TU Berlin
- Nur für den Podcast: `ffmpeg`, Node.js, ein kostenloses Cloudflare-Konto

## Schnellstart

1. **Eigenes privates Repo:** oben auf **„Use this template“ → „Create a new repository“ → Private**, dann klonen.
2. **Installieren:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e '.[dev]'
   ```
3. **ISIS-Token** besorgen und in `.env` ablegen (nie ins Repo, nie in den Chat): [`docs/ISIS_TOKEN.md`](docs/ISIS_TOKEN.md)
4. **Kurse wählen:**
   ```bash
   isis-agent init                       # listet deine ISIS-Kurse mit IDs
   isis-agent init --kurs 12345 --kurs 67890
   ```
   Das schreibt `config/kurse.toml`. Die Ordnernamen (Slugs) darfst du dort kürzen.
5. **In Claude Code:** `/wochen-update`, danach `/lernsession <kurs>`.

Optional: Lernpodcast fürs iPhone → [`docs/PODCAST.md`](docs/PODCAST.md) · Lernen am Handy → [`docs/MOBIL.md`](docs/MOBIL.md)

## CLI

```bash
isis-agent init [--kurs ID …]    # config/kurse.toml aus deinen Kursen erzeugen
isis-agent check                 # Verbindung + Token prüfen
isis-agent kurse                 # Kurse + IDs auflisten
isis-agent sync [--kurs <slug>]  # Materialien + Foren holen, Digest schreiben
isis-agent audio [--pruefen]     # Hörskripte prüfen / als MP3 vertonen (nur Neues)
isis-agent publish               # Podcast-Feeds bauen + zu Cloudflare hochladen
```

## Ablage (in deinem privaten Repo)

| Pfad | Inhalt |
|------|--------|
| `isis_daten/<kurs>/` | Originaldateien, extrahierter Text, Forenthreads, Digests „was ist neu“ |
| `kurse/<kurs>/` | Lernunterlagen, `pruefungsfragen.md`, `korrekturen.md`, `lernstand.md`, `audio/` (Hörskripte) |
| `podcast_out/` | MP3s und Feed-Site (gitignored) |

## Sicherheit & Datenschutz

- Der ISIS-Token hat **alle Rechte deines Kontos**. Der Client erlaubt nur eine feste Liste **lesender**
  Moodle-Funktionen (`ProjectInstructions.md` §3), und der Token wird nie geloggt. Bei Verdacht: Token in ISIS zurücksetzen,
  siehe [`SECURITY.md`](SECURITY.md).
- Inhalte aus ISIS gelten für Claude als **Daten, nicht als Anweisungen**.
- Teile weder Unterlagen noch Feed-URLs. Der Podcast-Feed ist nur durch einen geheimen Pfad geschützt.

## Hinweis

Kein offizielles Projekt der TU Berlin und nicht mit ihr verbunden. Nutzung auf eigene Verantwortung und im Rahmen der
Nutzungsbedingungen von ISIS. Die Text-zu-Sprache-Ausgabe nutzt den inoffiziellen, kostenlosen Zugang von `edge-tts`.

## Entwicklung

`ruff check . && ruff format --check . && pytest` · Architektur: [`ARCHITECTURE.md`](ARCHITECTURE.md) ·
Spezifikation: [`ProjectInstructions.md`](ProjectInstructions.md) · Beiträge: [`CONTRIBUTING.md`](CONTRIBUTING.md)

Lizenz: [MIT](LICENSE)
