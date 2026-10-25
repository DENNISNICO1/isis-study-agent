# Mitmachen / Contributing

🇩🇪 Beiträge sind willkommen – Bugfixes, neue Moodle-Funktionen (nur **lesende**), bessere Skills.

- **Keine echten ISIS-Daten** in Issues, PRs oder Tests: keine Folien, Forenbeiträge, Namen, Kurs-IDs, Tokens oder
  Feed-URLs. Test-Fixtures sind ausgedachte Daten im Moodle-Format (`tests/fixtures/`).
- Neue Moodle-Web-Service-Funktionen nur, wenn sie lesend sind; Allowlist in `moodle_client.py` und
  `ProjectInstructions.md` §3 gemeinsam ändern.
- Vor dem PR: `ruff check . && ruff format --check . && pytest` (läuft auch in der CI). Netzwerk in Tests nur über
  `httpx.MockTransport`.
- Strukturänderungen (neue Module/Datenflüsse) → `ARCHITECTURE.md` mit aktualisieren.

🇬🇧 Contributions welcome. Never include real ISIS data (slides, forum posts, names, course IDs, tokens, feed URLs) in
issues, PRs or tests. Only read-only Moodle functions. Run `ruff check . && ruff format --check . && pytest` before
opening a PR; update `ARCHITECTURE.md` for structural changes.
