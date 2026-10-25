"""Hilfsskript: ISIS-Token über den Moodle-Mobile-Launch-Flow holen und in .env speichern.

Läuft lokal auf deinem Rechner (nicht in der Cloud-Session),
weil du dich im Browser per TU-SSO anmeldest.

    python tools/token_holen.py

Der Token wird nie ausgegeben, sondern nur in die (gitignorte) .env geschrieben.
"""

import base64
import getpass
import hashlib
import secrets
import sys
from pathlib import Path
from urllib.parse import unquote

BASE_URL = "https://isis.tu-berlin.de"
SCHEME = "moodledownloader"


def launch_url(passport: str) -> str:
    return (
        f"{BASE_URL}/admin/tool/mobile/launch.php"
        f"?service=moodle_mobile_app&passport={passport}&urlscheme={SCHEME}"
    )


def parse_redirect(redirect: str, passport: str, base_url: str = BASE_URL) -> str:
    """Liest den Token aus 'moodledownloader://token=<base64>' und prüft die Signatur."""
    redirect = unquote(redirect.strip())
    marker = "token="
    if marker not in redirect:
        raise ValueError("Die eingefügte Adresse enthält kein 'token='.")
    encoded = redirect.split(marker, 1)[1].split("&", 1)[0].strip("/")
    decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
    parts = decoded.split(":::")
    if len(parts) < 2:
        raise ValueError("Unerwartetes Token-Format.")
    signature, token = parts[0], parts[1]
    expected = {
        hashlib.md5((u + passport).encode()).hexdigest() for u in (base_url, base_url + "/")
    }
    if signature not in expected:
        raise ValueError(
            "Signatur passt nicht – bitte mit einer frisch erzeugten Launch-URL neu versuchen."
        )
    return token


def write_env(token: str, env: Path) -> None:
    lines = []
    if env.is_file():
        lines = [
            ln
            for ln in env.read_text(encoding="utf-8").splitlines()
            if not ln.startswith("ISIS_TOKEN=")
        ]
    lines.append(f"ISIS_TOKEN={token}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    env.chmod(0o600)


def main() -> int:
    passport = secrets.token_hex(8)
    print("1. Öffne diese Adresse in deinem Browser und melde dich mit deinem TU-Account an:\n")
    print("   " + launch_url(passport) + "\n")
    print("2. Der Browser versucht danach, eine Adresse 'moodledownloader://token=…' zu öffnen")
    print("   (Fehlermeldung oder Nachfrage ist normal). Kopiere diese Adresse:")
    print("   - Chrome/Edge: F12 → Netzwerk → letzter Eintrag 'launch.php' → Header 'Location'")
    print("   - Firefox: F12 → Netzwerk → 'launch.php' → Antwort-Header 'Location'")
    print("3. Füge sie hier ein (Eingabe wird nicht angezeigt):")
    redirect = getpass.getpass("   > ")
    try:
        token = parse_redirect(redirect, passport)
    except ValueError as exc:
        print(f"Fehler: {exc}", file=sys.stderr)
        return 1
    env = Path(__file__).resolve().parents[1] / ".env"
    write_env(token, env)
    print(f"\nToken gespeichert in {env} (nicht committen; .env ist gitignored).")
    print("Für die Cloud-Umgebung: Wert aus .env als Environment variable ISIS_TOKEN eintragen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
