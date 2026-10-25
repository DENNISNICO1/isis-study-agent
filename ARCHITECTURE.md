# Architecture — isis-study-agent

> Living document. Update when adding modules/services, changing data flows, or refactoring responsibilities.

## Module Dependency Graph

```mermaid
flowchart TD
    CLI[cli.py] -->|liest, init schreibt kurse.toml| CFG[config.py]
    CLI --> SYNC[sync.py]
    CLI --> FOR[forums.py]
    CLI --> DIG[digest.py]
    CLI --> EX
    SYNC --> PA[paths.py]
    FOR --> HT[htmltext.py]
    SYNC --> MC[moodle_client.py]
    FOR --> MC
    SYNC --> ST[state.py]
    FOR --> ST
    EX[extract.py] --> HT
    MC -->|REST + wstoken| ISIS[(ISIS Moodle)]
    CMD[.claude wochen-update] -->|ruft auf| CLI
    CMD --> SK[Skill lernunterlagen]
    SK -->|schreibt| KURSE[kurse/ Lernunterlagen]
    LS[.claude lernsession] -->|liest| KURSE
```

## Audio & Podcast Modules

```mermaid
flowchart TD
    CLI[cli.py audio feed publish] --> HS[hoerskript.py]
    CLI --> AU[audio.py]
    CLI --> PC[podcast.py]
    CLI --> CFG[config.py podcast und PODCAST_SECRET]
    AU --> TTS[tts.py]
    AU -->|Montage und MP3-Kodierung| FF[(ffmpeg)]
    TTS -->|edge-tts| MS[(Microsoft Neural TTS)]
    TTS -->|say| MAC[(macOS Sprachausgabe)]
    PC -->|wrangler deploy mit cloudflare_worker.js| CF[(Cloudflare Worker mit Range-Support)]
    SK[Skill hoerskript] -->|schreibt| AUD[kurse/kurs/audio Hörskripte]
    HS -->|liest| AUD
    CF -->|RSS mit geheimem Pfad| APP[iPhone Podcast-App]
```

## Core Data Flow

```mermaid
flowchart TD
    A[Nutzer startet wochen-update] --> B[isis-agent sync]
    B --> C[Kursinhalte und Foren von ISIS]
    C --> D[Neue oder geänderte Dateien in isis_daten]
    D --> E[PDF-Text extrahieren]
    E --> F[Digest pro Kurs und Woche]
    F --> G[Claude liest Digest und Texte]
    G --> H[Wochenunterlagen, Prüfungsfragen, Korrekturen]
    H --> I[Commit und Push]
    I --> J[Lernsession mit Claude]
    H --> K[Skill hoerskript schreibt Hörskripte]
    K --> L[isis-agent audio vertont neue und geänderte Skripte]
    L --> M[isis-agent publish baut RSS und lädt zu Cloudflare]
    M --> N[Hören in der Podcast-App]
```

## Mobile Lernsession

```mermaid
flowchart TD
    P[iPhone Claude-App Code] -->|Cloud-Session im Repo| Q[lernsession mobil]
    Q -->|liest| R[kurse/kurs Unterlagen und lernstand]
    Q -->|push auf claude Branch| S[PR nach main]
    S -->|nächste Session sieht Lernstand| R
```
