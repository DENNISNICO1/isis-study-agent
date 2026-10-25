"""Foren und Ankündigungen: neue Diskussionen und Beiträge seit dem letzten Lauf."""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Kurs
from .htmltext import html_to_text
from .moodle_client import MoodleClient
from .paths import slugify
from .state import Manifest

log = logging.getLogger(__name__)

PER_PAGE = 50
MAX_PAGES = 10


@dataclass(frozen=True)
class NewPost:
    forum: str
    is_announcement: bool
    discussion: str
    subject: str
    author: str
    created: int
    text: str
    thread_file: Path  # relativ zum Kursverzeichnis


@dataclass
class ForumResult:
    posts: list[NewPost] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def sync_forums(
    client: MoodleClient, kurs: Kurs, kurs_dir: Path, manifest: Manifest
) -> ForumResult:
    result = ForumResult()
    forums = client.call("mod_forum_get_forums_by_courses", courseids=[kurs.id])
    for forum in forums:
        try:
            _sync_forum(client, forum, kurs_dir, manifest, result)
        except Exception as exc:  # ein kaputtes Forum soll die anderen nicht blockieren
            result.errors.append(f"Forum {forum.get('name')}: {exc}")
            log.warning("Forum-Sync fehlgeschlagen: %s", forum.get("name"))
    return result


def _sync_forum(
    client: MoodleClient,
    forum: dict[str, Any],
    kurs_dir: Path,
    manifest: Manifest,
    result: ForumResult,
) -> None:
    forum_name = forum.get("name", "Forum")
    is_news = forum.get("type") == "news"
    forum_dir = Path("forum") / slugify(forum_name)
    for discussion in _changed_discussions(client, forum["id"], manifest):
        disc_id = str(discussion["discussion"])
        known = manifest.discussions.get(disc_id, {})
        seen = set(known.get("post_ids", []))
        posts = client.call("mod_forum_get_discussion_posts", discussionid=int(disc_id))["posts"]
        posts.sort(key=lambda p: p.get("timecreated", 0))
        rel = forum_dir / f"{disc_id}-{slugify(discussion.get('name', ''))}.md"
        _write_thread(kurs_dir, rel, forum_name, discussion, posts)
        for post in posts:
            if post["id"] in seen:
                continue
            result.posts.append(
                NewPost(
                    forum=forum_name,
                    is_announcement=is_news,
                    discussion=discussion.get("name", ""),
                    subject=post.get("subject", ""),
                    author=_author(post),
                    created=int(post.get("timecreated", 0)),
                    text=html_to_text(post.get("message")),
                    thread_file=rel,
                )
            )
        manifest.discussions[disc_id] = {
            "forum": forum_name,
            "timemodified": discussion.get("timemodified"),
            "post_ids": sorted(p["id"] for p in posts),
        }


def _changed_discussions(client: MoodleClient, forum_id: int, manifest: Manifest) -> list[dict]:
    """Diskussionen (neueste zuerst), deren timemodified sich seit dem letzten Lauf geändert hat."""
    changed: list[dict] = []
    for page in range(MAX_PAGES):
        data = client.call(
            "mod_forum_get_forum_discussions", forumid=forum_id, page=page, perpage=PER_PAGE
        )
        batch = data.get("discussions", [])
        fresh = [
            d
            for d in batch
            if manifest.discussions.get(str(d["discussion"]), {}).get("timemodified")
            != d.get("timemodified")
        ]
        changed += fresh
        # Sortierung nach letzter Aktivität: eine Seite ohne Änderungen beendet die Suche.
        if len(batch) < PER_PAGE or not fresh:
            break
    return changed


def _author(post: dict[str, Any]) -> str:
    author = post.get("author") or {}
    return author.get("fullname") or post.get("userfullname") or "unbekannt"


def _write_thread(
    kurs_dir: Path, rel: Path, forum_name: str, discussion: dict, posts: list[dict]
) -> None:
    lines = [f"# {discussion.get('name', '')}", "", f"Forum: {forum_name}", ""]
    for post in posts:
        when = _fmt(post.get("timecreated"))
        lines += [f"## {post.get('subject', '')}", f"*{_author(post)} – {when}*", ""]
        lines += [html_to_text(post.get("message")), ""]
    path = kurs_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    raw = {"discussion": discussion, "posts": posts}
    path.with_suffix(".json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _fmt(ts: Any) -> str:
    if not ts:
        return "?"
    return datetime.fromtimestamp(int(ts), UTC).strftime("%Y-%m-%d %H:%M UTC")
