# Lernpodcast einrichten (iPhone, kostenlos)

Die Wochenunterlagen werden als privater Podcast hörbar: Claude schreibt pro Woche ein **Hörskript**
(`kurse/<kurs>/audio/*-hoer.md`), `isis-agent audio` vertont es, `isis-agent publish` lädt die Folgen samt
RSS-Feed zu **Cloudflare** hoch (ein Worker, der nur statische Dateien ausliefert). Auf dem iPhone abonnierst du den Feed in Apple Podcasts oder Overcast.

```
Wochendatei ──Skill hoerskript──► Hörskript ──isis-agent audio──► MP3 (Kapitel) ──isis-agent publish──► Cloudflare Worker ──RSS──► iPhone
```

**Kosten:** keine. edge-tts nutzt die kostenlosen Microsoft-Neural-Stimmen (ohne Key, inoffiziell; Ausweichlösung:
`--backend say`). Cloudflare Workers Static Assets sind im Free-Plan kostenlos und unbegrenzt abrufbar (Dateien bis 25 MB).
> Hinweis: Cloudflare Pages ist inzwischen in Workers aufgegangen; `wrangler pages …` leitet nur noch weiter
> und scheitert ohne Projekt-Konfiguration. Deshalb lädt `isis-agent publish` direkt als Worker hoch.
> Ein kleines Skript (`src/isis_agent/cloudflare_worker.js`) beantwortet dabei Range-Anfragen, die Static
> Assets allein nicht unterstützen – ohne sie streamt/spult der iPhone-Player nicht zuverlässig.

## Einmalige Einrichtung (Mac)

1. **Werkzeuge:** `brew install ffmpeg node` und `pip install -e '.[dev]'` (installiert `edge-tts`).
2. **Geheimen Pfad erzeugen** und in `.env` eintragen (nie committen):
   ```bash
   python -c "import secrets; print('PODCAST_SECRET=' + secrets.token_urlsafe(24))" >> .env
   ```
3. **Cloudflare** (kostenloses Konto auf dash.cloudflare.com, keine Kreditkarte nötig):
   ```bash
   npx wrangler login     # öffnet den Browser
   ```
   Neues Konto: einmalig unter dash.cloudflare.com → *Workers & Pages* eine **workers.dev-Subdomain** wählen
   (erscheint in der Feed-URL). Ein Projekt muss nicht angelegt werden: Der erste `isis-agent publish` (solange `site_url` leer ist) lädt ein
   leeres Grundgerüst als Worker `isis-lernpodcast` hoch und gibt dessen Adresse aus
   (`https://isis-lernpodcast.<konto>.workers.dev`). Diese als `podcast.site_url` in `config/kurse.toml` eintragen.
4. **Erste Folgen:**
   ```bash
   isis-agent audio --pruefen   # Format der Hörskripte prüfen
   isis-agent audio             # vertonen (nur neue/geänderte Skripte)
   isis-agent publish           # Feeds bauen + hochladen, gibt die Feed-URLs aus
   ```

## iPhone

- **Apple Podcasts:** Tab *Mediathek* → oben rechts `…` → *Sendung per URL folgen* → Feed-URL einfügen.
  Pro Kurs ein Feed (`…/<secret>/<kurs>/feed.xml`); `isis-agent feed` zeigt die URLs.
- **Overcast** (Alternative mit Kapitelliste und „Smart Speed“): `+` → *Add URL*.
- Empfehlung: Automatische Downloads an (offline in der U-Bahn), Tempo 1,1–1,25×.
- Die Folgen haben **Kapitel** (eines pro Konzept, dazu Quiz und Zusammenfassung), damit du gezielt springen kannst.
- Im **Prüfungsquiz** gibt es nach jeder Frage eine Pause. Antworte laut, dann kommt die Musterantwort.

## Wöchentlich

`/wochen-update` schreibt die Hörskripte automatisch. Lokal vertont und veröffentlicht es auch, wenn
`PODCAST_SECRET` und `site_url` gesetzt sind. Sonst manuell: `isis-agent audio && isis-agent publish`.

## Optionen (`config/kurse.toml` → `[podcast]`)

| Schlüssel | Bedeutung |
|---|---|
| `stimme` | edge-Stimme: `de-DE-KatjaNeural` (Standard), `de-DE-ConradNeural`, `de-DE-AmalaNeural`, `de-DE-KillianNeural`. **Keine `…Multilingual…`-Stimmen**: edge-tts sendet fest Englisch als Sprache, die lesen Deutsch dann mit englischer Aussprache (wird abgelehnt). |
| `tempo` | Sprechtempo, z. B. `+10%` |
| `backend` | `edge` (online, beste Qualität) oder `say` (macOS, offline; Stimme z. B. `Anna`) |

Eine geänderte Stimme oder ein geändertes Tempo führt dazu, dass alle Folgen neu vertont werden. `isis-agent audio --neu` erzwingt das.

## Sicherheit & Urheberrecht

- Der Feed ist **nicht passwortgeschützt** (Podcast-Apps können kein Login). Geschützt wird er nur durch den
  unerratbaren Pfad, `robots.txt` und `noindex`-Header sowie `itunes:block` (keine Aufnahme in Verzeichnisse).
  Wer die URL kennt, kann die Folgen hören → **URL nicht teilen**, nicht in Repo/Chat/Issues schreiben.
- Die Inhalte stammen aus Vorlesungsmaterial: nur für dich, nicht weitergeben.
- **Secret wechseln** (falls die URL bekannt wurde): neues `PODCAST_SECRET` in `.env` eintragen, `isis-agent publish`,
  in der Podcast-App neu abonnieren. Vorschau-URLs alter Versionen sind abgeschaltet (`preview_urls: false` in
  `podcast_out/wrangler.jsonc`), alte Dateien sind nach dem Upload also nicht mehr erreichbar.
- `podcast_out/` (MP3s und Site) ist gitignored.

## Fehlerbehebung

| Meldung | Lösung |
|---|---|
| `edge-tts nicht erreichbar` | Netzwerk prüfen; notfalls `isis-agent audio --backend say` |
| `ffmpeg nicht gefunden` | `brew install ffmpeg` |
| `nicht sprechbare Zeichen …` | Hörskript an der genannten Zeile in gesprochene Sprache umformulieren (Skill `hoerskript`) |
| `PODCAST_SECRET … müssen gesetzt sein` | Schritte 2–3 oben |
| `Upload zu Cloudflare fehlgeschlagen` | `npx wrangler login`; Worker-Name in `cloudflare_projekt` schon von einem anderen Projekt im Konto belegt? |
| Folge > 25 MB | Hörskript kürzen oder auf zwei Folgen aufteilen (≈ 50 min Grenze bei 64 kbit/s) |
