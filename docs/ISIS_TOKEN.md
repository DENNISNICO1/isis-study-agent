# ISIS-Token besorgen und hinterlegen

Der Agent spricht mit ISIS über die Moodle-Web-Service-API. Dafür braucht er einen persönlichen Token
(den gleichen, den die Moodle-App nutzt). **Der Token hat die Rechte deines Kontos:** nie in den Chat,
nie ins Repo. Der Agent nutzt im Code nur lesende Funktionen.

## Weg A: Sicherheitsschlüssel-Seite (am einfachsten, falls vorhanden)
1. In ISIS einloggen → oben rechts Profilbild → **Einstellungen** → **Sicherheitsschlüssel**
   (direkt: <https://isis.tu-berlin.de/user/managetoken.php>).
2. Steht dort ein Schlüssel für **„Moodle mobile web service“**, ist das dein Token.
3. Fehlt die Seite oder der Eintrag → Weg B.

## Weg B: Launch-Flow mit Hilfsskript (lokal am Rechner)
```bash
git clone <dieses Repo> && cd isis-study-agent
python3 tools/token_holen.py
```
Das Skript zeigt eine Adresse, du loggst dich per TU-SSO ein, kopierst die Weiterleitungsadresse
`moodledownloader://token=…` aus den Entwicklertools (F12 → Netzwerk → `launch.php` → Header `Location`)
und fügst sie verdeckt ein. Der Token landet in `.env` (gitignored), ohne angezeigt zu werden.

Ohne Repo geht es auch per Handy: die Moodle-App nutzt denselben Weg, zeigt den Token aber nicht an.
Weg B ist deshalb der zuverlässige Fallback.

## Token hinterlegen
- **Lokal:** `.env` mit `ISIS_TOKEN=…` (siehe `.env.example`).
- **Claude-Cloud-Umgebung:** claude.ai/code → Pfeil ▾ neben dem Session-Titel → **Edit cloud environment**
  → **Environment variables** → Zeile `ISIS_TOKEN=…` → speichern → **neue Session** starten.
  (Network secrets passen hier nicht, weil Moodle den Token als Parameter statt als Header erwartet.)
- Zusätzlich muss unter **Network access** → **Custom** die Domain `isis.tu-berlin.de` erlaubt sein
  (Haken „Also include default list of common package managers“ gesetzt lassen).

## Prüfen
```bash
isis-agent check    # zeigt „Angemeldet als …“
isis-agent kurse    # listet Kurse + IDs → in config/kurse.toml eintragen
```

## Token widerrufen
Bei Verdacht auf Missbrauch: Sicherheitsschlüssel-Seite → Token zurücksetzen, oder in der Moodle-App abmelden.
