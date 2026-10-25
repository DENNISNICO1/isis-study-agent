# Sicherheit / Security

🇩🇪 **Token geleakt?** Wenn dein ISIS-Token (`ISIS_TOKEN`) in ein Repo, einen Chat oder ein Log geraten ist:
1. In ISIS → Profil → Einstellungen → **Sicherheitsschlüssel** den Schlüssel für „Moodle mobile web service“
   **zurücksetzen** (oder in der Moodle-App abmelden). Der alte Token ist danach ungültig.
2. Neuen Token wie in [`docs/ISIS_TOKEN.md`](docs/ISIS_TOKEN.md) holen und in `.env` eintragen.
3. Liegt er in der Git-Historie: Repo-Historie bereinigen (z. B. `git filter-repo`) – Zurücksetzen (1.) bleibt Pflicht.

**Podcast-Feed-URL geteilt?** Neues `PODCAST_SECRET` in `.env`, `isis-agent publish`, in der Podcast-App neu abonnieren.

**Sicherheitslücke im Code gefunden?** Bitte nicht als öffentliches Issue, sondern über
GitHub → *Security* → **Report a vulnerability** (private Meldung) melden.

---

🇬🇧 **Leaked token?** Reset the "Moodle mobile web service" key in ISIS → Preferences → *Security keys* (or log out of
the Moodle app), fetch a new token per [`docs/ISIS_TOKEN.md`](docs/ISIS_TOKEN.md), and clean your git history if needed.
**Leaked feed URL?** Set a new `PODCAST_SECRET`, run `isis-agent publish`, resubscribe.
**Found a vulnerability?** Please report it privately via GitHub → *Security* → **Report a vulnerability**, not as a
public issue.
