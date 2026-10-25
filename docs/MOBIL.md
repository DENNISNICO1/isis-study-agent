# Lernen unterwegs (iPhone)

Drei Wege, von passiv bis interaktiv. Alle sind ohne Zusatzkosten (über das bestehende Claude-Abo).

## 1. Hören: Lernpodcast

Vertonte Wochenunterlagen mit Kapiteln und Prüfungsquiz in Apple Podcasts oder Overcast. Einrichtung: [`docs/PODCAST.md`](PODCAST.md).

## 2. Tippen: `/lernsession` mit Claude Code auf dem Handy

Claude Code läuft auch in der Claude-iOS-App (Bereich *Code*) bzw. unter claude.ai/code im Browser.

1. Einmalig dein **privates** GitHub-Repo (aus „Use this template“) verbinden und eine Umgebung anlegen.
   Für Lernsessions braucht es **keinen** `ISIS_TOKEN` und keine besondere Netzwerkfreigabe.
2. Neue Session im Repo starten und z. B. schreiben: `/lernsession <kurs> mobil`.
3. „mobil“ schaltet auf kurze Nachrichten ohne Tabellen und große Formelblöcke um.
4. Am Ende wird `lernstand.md` auf einen `claude/…`-Branch gepusht. Übernimm den Stand per **PR nach `main`**
   (Button in der App), damit die nächste Session (auch am Mac) deine Schwächen kennt.

`/wochen-update` besser am Mac ausführen: Dort liegen `.env` mit dem ISIS-Token, ffmpeg und das Cloudflare-Login.
In einer Cloud-Session schreibt es nur die Hörskripte. Vertont wird später lokal.

**Alternative:** `claude remote-control` am Mac starten und die laufende Session vom Handy aus steuern.
Dafür muss der Mac an sein, dafür ist alles da (Token, ffmpeg, Podcast-Upload).

## 3. Sprechen: Claude-App im Sprachmodus

Für eine echte **mündliche Prüfungssimulation** unterwegs, mit Kopfhörern und ohne Bildschirm:

1. Auf claude.ai ein Projekt „Lernsession <Kurs>“ anlegen.
2. Als Projektwissen die Dateien aus `kurse/<kurs>/` hinzufügen (GitHub-Integration oder Upload):
   Wochendateien, `pruefungsfragen.md`, `korrekturen.md`, `lernstand.md`.
3. Als Projekt-Anweisung den Abschnitt „Ablauf“ aus `.claude/commands/lernsession.md` einfügen, ergänzt um:
   *„Wir sprechen per Sprachmodus: kurze Sätze, Formeln in Worten, eine Frage pro Runde.“*
4. In der Claude-App den **Sprachmodus** starten. Claude fragt wie in der mündlichen Prüfung, du antwortest laut.

Diese Variante schreibt `lernstand.md` nicht automatisch. Am Ende kannst du dir eine Zusammenfassung der Schwächen geben
lassen und sie in der nächsten `/lernsession` nachtragen lassen.
