"""Kommandozeile: isis-agent init | check | kurse | sync | audio | feed | publish."""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import hoerskript
from .audio import AudioError, Ffmpeg, render_folge
from .config import (
    Config,
    ConfigError,
    Kurs,
    env_value,
    load_config,
    load_token,
    render_config,
)
from .digest import render_digest, week_label, write_digest
from .extract import extract
from .forums import ForumResult, sync_forums
from .hoerskript import HoerskriptError
from .moodle_client import ALLOWED_FUNCTIONS, MoodleClient, MoodleError
from .paths import slugify
from .podcast import (
    Episode,
    Katalog,
    PodcastError,
    basis_site,
    baue_site,
    deploy_cloudflare,
    skript_hash,
)
from .state import Manifest
from .sync import SyncResult, sync_material
from .tts import TTSError, get_backend

DATA_DIR = "isis_daten"
CONFIG_PATH = Path("config") / "kurse.toml"
DEFAULT_BASE_URL = "https://isis.tu-berlin.de"
KURSE_DIR = "kurse"
PODCAST_DIR = "podcast_out"
SECRET_ENV = "PODCAST_SECRET"


def _client(cfg: Config, root: Path) -> MoodleClient:
    return MoodleClient(cfg.base_url, load_token(root / ".env"))


def cmd_check(cfg: Config, root: Path, _args: argparse.Namespace) -> int:
    with _client(cfg, root) as client:
        info = client.call("core_webservice_get_site_info")
    print(f"Verbunden mit {info.get('sitename')} (Moodle {info.get('release', '?')})")
    print(f"Angemeldet als {info.get('fullname')} ({info.get('username')})")
    available = {f.get("name") for f in info.get("functions", [])}
    missing = sorted(ALLOWED_FUNCTIONS - available) if available else []
    if missing:
        print("Nicht verfügbare Funktionen (werden ggf. übersprungen): " + ", ".join(missing))
    return 0


def _eigene_kurse(client: MoodleClient) -> list[dict]:
    info = client.call("core_webservice_get_site_info")
    courses = client.call("core_enrol_get_users_courses", userid=info["userid"])
    return sorted(courses, key=lambda c: c.get("fullname", ""))


def _eindeutige_slugs(namen: list[str]) -> list[str]:
    slugs: list[str] = []
    for name in namen:
        basis = slugify(name, max_len=40)
        slug, n = basis, 2
        while slug in slugs:
            slug, n = f"{basis}-{n}", n + 1
        slugs.append(slug)
    return slugs


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    """Erzeugt config/kurse.toml aus den eigenen ISIS-Kursen (ohne vorhandene Konfiguration)."""
    path = root / CONFIG_PATH
    if args.kurs and path.exists() and not args.force:
        raise ConfigError(f"{CONFIG_PATH} existiert bereits – mit --force überschreiben")
    with MoodleClient(args.base_url, load_token(root / ".env")) as client:
        courses = _eigene_kurse(client)
    if not args.kurs:
        print("Deine ISIS-Kurse:")
        for c in courses:
            print(f"  id={c['id']:>6}  {c.get('fullname')}")
        print("\nWeiter mit: isis-agent init --kurs <id> --kurs <id> …")
        return 0
    by_id = {c["id"]: c for c in courses}
    fehlend = [str(i) for i in args.kurs if i not in by_id]
    if fehlend:
        raise ConfigError(f"Nicht in deinen Kursen: {', '.join(fehlend)} (siehe `isis-agent init`)")
    gewaehlt = [by_id[i] for i in args.kurs]
    slugs = _eindeutige_slugs([c.get("fullname", str(c["id"])) for c in gewaehlt])
    kurse = [
        Kurs(slug=slug, name=c.get("fullname", slug), id=c["id"], suche=c.get("fullname", slug))
        for slug, c in zip(slugs, gewaehlt, strict=True)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_config(args.base_url, kurse), encoding="utf-8")
    print(f"✅ {CONFIG_PATH} geschrieben:")
    for k in kurse:
        print(f"  {k.slug}  ←  {k.name}")
    print(
        "Slugs (Ordnernamen) darfst du kürzen, z. B. 'stroemungsakustik'. Weiter: isis-agent sync"
    )
    return 0


def cmd_kurse(cfg: Config, root: Path, _args: argparse.Namespace) -> int:
    with _client(cfg, root) as client:
        courses = _eigene_kurse(client)
    print("Deine ISIS-Kurse:")
    for c in courses:
        matches = [k.slug for k in cfg.kurse if k.suche.lower() in c.get("fullname", "").lower()]
        mark = f"  ← passt zu '{matches[0]}'" if matches else ""
        print(f"  id={c['id']:>6}  {c.get('fullname')}{mark}")
    print("\nTrage die passenden IDs in config/kurse.toml ein.")
    return 0


def cmd_sync(cfg: Config, root: Path, args: argparse.Namespace) -> int:
    kurse = [cfg.kurs(args.kurs)] if args.kurs else cfg.kurse
    now = datetime.now(UTC)
    status = 0
    with _client(cfg, root) as client:
        for kurs in kurse:
            if not kurs.hat_id:
                print(
                    f"⏭  {kurs.name}: keine Kurs-ID in config/kurse.toml (siehe `isis-agent kurse`)"
                )
                status = 1
                continue
            path = sync_course(client, kurs, root / DATA_DIR, now, args)
            print(f"✅ {kurs.name}: Digest {path.relative_to(root)}")
    return status


def sync_course(
    client: MoodleClient, kurs: Kurs, data_dir: Path, now: datetime, args: argparse.Namespace
) -> Path:
    kurs_dir = data_dir / kurs.slug
    manifest = Manifest.load(kurs_dir / ".state" / "manifest.json")
    first_run = not manifest.runs
    material: SyncResult | None = None
    forums: ForumResult | None = None
    if not args.nur_forum:
        material = sync_material(client, kurs, kurs_dir, manifest)
    if not args.nur_material:
        forums = sync_forums(client, kurs, kurs_dir, manifest)
    texts = {c.path: extract(kurs_dir, c.path) for c in (material.changes if material else [])}
    body = render_digest(kurs, kurs_dir, material, forums, texts, now, first_run)
    label = week_label(now)
    digest = write_digest(kurs_dir, label, kurs, body)
    manifest.runs.append(
        {
            "at": now.isoformat(timespec="seconds"),
            "week": label,
            "files_changed": len(material.changes) if material else 0,
            "new_posts": len(forums.posts) if forums else 0,
        }
    )
    manifest.save()
    return digest


def _lade_skript(kurs: Kurs, path: Path, root: Path) -> tuple[str, hoerskript.Hoerskript]:
    rel = path.relative_to(root)
    text = path.read_text(encoding="utf-8")
    skript = hoerskript.parse(text, name=str(rel))
    if skript.kurs != kurs.slug:
        raise HoerskriptError(f"{rel}: kurs '{skript.kurs}' ≠ Ordner '{kurs.slug}'")
    return text, skript


def _episode_key(kurs: Kurs, path: Path) -> str:
    return f"{kurs.slug}/{path.stem.removesuffix('-hoer')}"


def cmd_audio(cfg: Config, root: Path, args: argparse.Namespace) -> int:
    """Prüft alle Hörskripte und vertont neue/geänderte als MP3-Folgen."""
    pc = cfg.podcast
    backend_name = args.backend or pc.backend
    stimme = pc.stimme if backend_name == pc.backend else ""
    backend = get_backend(backend_name, stimme or None, pc.tempo)
    out_dir = root / PODCAST_DIR
    katalog = Katalog.load(out_dir / ".state" / "episoden.json")
    now = datetime.now(UTC).replace(microsecond=0)
    status, gefunden = 0, set()
    kurse = [cfg.kurs(args.kurs)] if args.kurs else cfg.kurse
    paare = [(k, p) for k in kurse for p in hoerskript.find_skripte(root / KURSE_DIR, k.slug)]
    if not paare:
        print("Keine Hörskripte gefunden (kurse/<kurs>/audio/*-hoer.md, Skill hoerskript).")
    for i, (kurs, path) in enumerate(paare):
        rel = path.relative_to(root)
        try:
            text, skript = _lade_skript(kurs, path, root)
        except HoerskriptError as exc:
            print(f"❌ {exc}", file=sys.stderr)
            status = 1
            continue
        key = _episode_key(kurs, path)
        gefunden.add(key)
        if args.pruefen:
            print(f"✅ {rel}: {len(skript.kapitel)} Kapitel, ~{skript.minuten():.0f} min")
            continue
        hash_ = skript_hash(text, backend.name, getattr(backend, "stimme", ""), pc.tempo)
        if not args.neu and not katalog.braucht_render(key, hash_, out_dir):
            print(f"⏭  {rel}: unverändert")
            continue
        print(f"🎙  {rel}: vertone mit {backend.name} …", flush=True)
        datei = Path("episoden") / kurs.slug / f"{key.split('/')[1]}.mp3"
        folge = render_folge(skript, backend, out_dir / datei, Ffmpeg(), kurs.name, pc.autor)
        katalog.episoden[key] = Episode(
            key=key,
            kurs=kurs.slug,
            titel=skript.titel,
            datei=datei.as_posix(),
            groesse=folge.groesse,
            dauer_s=round(folge.dauer_s, 1),
            hash=hash_,
            veroeffentlicht=(now + timedelta(seconds=i)).isoformat(),
            beschreibung="Kapitel: " + " · ".join(k.titel for k in skript.kapitel),
        )
        katalog.save()
        print(f"   → {datei} ({folge.dauer_s / 60:.1f} min, {folge.groesse / 1e6:.1f} MB)")
    if not args.pruefen and status == 0:
        _entferne_verwaiste(katalog, out_dir, gefunden, {k.slug for k in kurse})
    return status


def _entferne_verwaiste(katalog: Katalog, out_dir: Path, gefunden: set[str], kurse: set[str]):
    """Folgen, deren Hörskript gelöscht wurde, aus Katalog und Ausgabe entfernen."""
    for key, ep in list(katalog.episoden.items()):
        if ep.kurs in kurse and key not in gefunden:
            (out_dir / ep.datei).unlink(missing_ok=True)
            del katalog.episoden[key]
            print(f"🗑  {key}: Hörskript gelöscht – Folge entfernt")
    katalog.save()


def cmd_feed(cfg: Config, root: Path, _args: argparse.Namespace) -> int:
    """Baut podcast_out/site/<secret>/<kurs>/feed.xml aus dem Episodenkatalog."""
    secret = env_value(SECRET_ENV, root / ".env")
    if not secret or not cfg.podcast.site_url:
        raise ConfigError(
            f"{SECRET_ENV} (.env) und podcast.site_url (config/kurse.toml) müssen gesetzt sein "
            "– siehe docs/PODCAST.md"
        )
    out_dir = root / PODCAST_DIR
    katalog = Katalog.load(out_dir / ".state" / "episoden.json")
    kurse = [(k.slug, k.name) for k in cfg.kurse]
    feeds = baue_site(
        out_dir, katalog, kurse, secret, cfg.podcast.site_url, cfg.podcast.autor, datetime.now(UTC)
    )
    if not feeds:
        print("Noch keine Folgen – zuerst `isis-agent audio`.")
        return 1
    print("Feeds (privat, nicht teilen; Apple Podcasts → Mediathek → … → Sendung per URL folgen):")
    for slug, url in feeds.items():
        print(f"  {slug}: {url}")
    return 0


def cmd_publish(cfg: Config, root: Path, args: argparse.Namespace) -> int:
    """Baut den Feed und lädt die Site zu Cloudflare (Worker mit Static Assets) hoch."""
    if not cfg.podcast.site_url:
        # Erster Upload: Die workers.dev-Adresse, die die Feeds brauchen, gibt es erst danach.
        deploy_cloudflare(basis_site(root / PODCAST_DIR), cfg.podcast.cloudflare_projekt)
        print(
            "Grundgerüst hochgeladen. Trage die oben ausgegebene https://…workers.dev-Adresse als "
            "podcast.site_url in config/kurse.toml ein und führe `isis-agent publish` erneut aus."
        )
        return 1
    status = cmd_feed(cfg, root, args)
    if status:
        return status
    deploy_cloudflare(root / PODCAST_DIR / "site", cfg.podcast.cloudflare_projekt)
    print("✅ Hochgeladen. Neue Folgen erscheinen beim nächsten Aktualisieren der Podcast-App.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="isis-agent", description="ISIS-Sync für Lernunterlagen")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Projektverzeichnis")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="config/kurse.toml aus deinen ISIS-Kursen erzeugen")
    init.add_argument("--kurs", type=int, action="append", help="Kurs-ID (mehrfach möglich)")
    init.add_argument("--force", action="store_true", help="vorhandene Konfiguration überschreiben")
    init.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Moodle-Adresse")
    sub.add_parser("check", help="Verbindung und Token prüfen")
    sub.add_parser("kurse", help="Eingeschriebene Kurse mit IDs auflisten")
    sync = sub.add_parser("sync", help="Materialien und Foren synchronisieren, Digest schreiben")
    sync.add_argument("--kurs", help="nur diesen Kurs (Slug)")
    only = sync.add_mutually_exclusive_group()
    only.add_argument("--nur-material", action="store_true")
    only.add_argument("--nur-forum", action="store_true")
    audio = sub.add_parser("audio", help="Hörskripte prüfen und als MP3-Folgen vertonen")
    audio.add_argument("--kurs", help="nur diesen Kurs (Slug)")
    audio.add_argument("--backend", choices=["edge", "say"], help="TTS-Backend (Standard: Konfig)")
    audio.add_argument("--pruefen", action="store_true", help="nur Format prüfen, nichts vertonen")
    audio.add_argument("--neu", action="store_true", help="alle Folgen neu vertonen")
    sub.add_parser("feed", help="Podcast-Feeds unter podcast_out/site bauen")
    sub.add_parser("publish", help="Feeds bauen und zu Cloudflare hochladen")
    return parser


COMMANDS = {
    "check": cmd_check,
    "kurse": cmd_kurse,
    "sync": cmd_sync,
    "audio": cmd_audio,
    "feed": cmd_feed,
    "publish": cmd_publish,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )
    root = args.root.resolve()
    try:
        if args.cmd == "init":
            return cmd_init(root, args)
        cfg = load_config(root / CONFIG_PATH)
        return COMMANDS[args.cmd](cfg, root, args)
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
    except MoodleError as exc:
        hint = (
            " → Token ungültig/abgelaufen, siehe docs/ISIS_TOKEN.md"
            if "token" in exc.errorcode
            else ""
        )
        print(f"ISIS-Fehler {exc}{hint}", file=sys.stderr)
    except (TTSError, AudioError) as exc:
        print(f"Audiofehler: {exc}", file=sys.stderr)
    except PodcastError as exc:
        print(f"Podcast-Fehler: {exc}", file=sys.stderr)
    except RuntimeError as exc:
        print(f"Verbindungsfehler: {exc}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
