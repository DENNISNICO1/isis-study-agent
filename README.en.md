# isis-study-agent

[🇩🇪 Deutsch](README.md) · 🇬🇧 English

A study agent for **ISIS (TU Berlin's Moodle)** that works with [Claude Code](https://claude.com/claude-code).
It syncs your courses (slides, exercises, links, forums, announcements) and has Claude turn them into weekly
**study notes that actually teach**, with forum corrections highlighted and questions for **oral exams**.
It also offers interactive **study sessions** (on your phone too) and an optional private **study podcast** for iPhone.

> [!IMPORTANT]
> **Your repository must stay private.** Course materials are copyrighted and forum posts contain other people's
> personal data. Use **"Use this template" → Private**, **not "Fork"**: a fork of a public repository is public.

> [!NOTE]
> Generated content (study notes, quiz questions, podcast) and the Claude workflows are in **German** by default.
> To get English output, tell Claude in your session (e.g. "write the notes in English"), or adjust the language
> lines in `.claude/skills/*/SKILL.md` and `.claude/commands/*.md` in your private copy.

## What you get

| Command | What it does |
|---|---|
| `/wochen-update` (weekly update) | Sync ISIS (new/changed items only), write study notes, exam questions, corrections and audio scripts |
| `/lernsession <course>` (study session) | Claude examines you like an oral exam, Socratic, one question at a time, and logs weak spots |
| `isis-agent audio` / `publish` | Turn audio scripts into MP3s with chapters (free TTS) and publish a private podcast feed |

## Requirements

- Python ≥ 3.12, Git, **Claude Code** access (subscription; no separate API key needed)
- A TU Berlin ISIS account
- Podcast only: `ffmpeg`, Node.js, a free Cloudflare account

## Quick start

1. **Your own private repo:** click **"Use this template" → "Create a new repository" → Private**, then clone it.
2. **Install:**
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e '.[dev]'
   ```
3. **Get your ISIS token** and put it into `.env` (never commit it, never paste it into a chat): [`docs/ISIS_TOKEN.md`](docs/ISIS_TOKEN.md) (German)
4. **Choose your courses:**
   ```bash
   isis-agent init                       # lists your ISIS courses with IDs
   isis-agent init --kurs 12345 --kurs 67890
   ```
   This writes `config/kurse.toml`. You may shorten the folder names (slugs) there.
5. **In Claude Code:** `/wochen-update`, then `/lernsession <course>`.

Optional: iPhone study podcast → [`docs/PODCAST.md`](docs/PODCAST.md) · Studying on your phone → [`docs/MOBIL.md`](docs/MOBIL.md) (both German)

## CLI

```bash
isis-agent init [--kurs ID …]    # create config/kurse.toml from your courses
isis-agent check                 # check connection + token
isis-agent kurse                 # list courses + IDs
isis-agent sync [--kurs <slug>]  # fetch materials + forums, write a digest
isis-agent audio [--pruefen]     # validate audio scripts / render MP3s (new ones only)
isis-agent publish               # build podcast feeds + upload to Cloudflare
```

## Security & privacy

- The ISIS token carries **all permissions of your account**. The client only allows a fixed list of **read-only**
  Moodle functions (`ProjectInstructions.md` §3) and never logs the token. If in doubt, reset it in ISIS,
  see [`SECURITY.md`](SECURITY.md).
- Content from ISIS is treated by Claude as **data, not instructions**.
- Don't share notes or feed URLs. The podcast feed is only protected by a secret path.

## Disclaimer

Not an official TU Berlin project and not affiliated with TU Berlin. Use at your own risk and within ISIS's terms of
use. Text-to-speech uses the unofficial free access provided by `edge-tts`.

## Development

`ruff check . && ruff format --check . && pytest` · Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md) ·
Spec: [`ProjectInstructions.md`](ProjectInstructions.md) · Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md)

License: [MIT](LICENSE)
