from isis_agent.forums import sync_forums
from isis_agent.state import Manifest

from .conftest import fixture


def discussions(form):
    if form["forumid"] == "100":
        return {
            "discussions": [
                {"id": 1, "discussion": 500, "name": "Termin verschoben", "timemodified": 10}
            ]
        }
    return {"discussions": [{"id": 2, "discussion": 600, "name": "Folie 12", "timemodified": 20}]}


POSTS = {
    "500": [
        {
            "id": 1,
            "subject": "Termin verschoben",
            "message": "<p>Die VL am 3.11. entfällt.</p>",
            "author": {"fullname": "Prof. Weinzierl"},
            "timecreated": 1760000000,
        }
    ],
    "600": [
        {
            "id": 2,
            "subject": "Folie 12",
            "message": "<p>Ist das Vorzeichen falsch?</p>",
            "author": {"fullname": "Student A"},
            "timecreated": 1760000100,
        },
        {
            "id": 3,
            "subject": "Re: Folie 12",
            "message": "<p>Ja, richtig ist <i>minus</i>.</p>",
            "author": {"fullname": "Tutor B"},
            "timecreated": 1760000200,
        },
    ],
}


def setup_fake(fake):
    fake.responses["mod_forum_get_forums_by_courses"] = fixture("forums.json")
    fake.responses["mod_forum_get_forum_discussions"] = discussions
    fake.responses["mod_forum_get_discussion_posts"] = lambda f: {"posts": POSTS[f["discussionid"]]}


def test_first_forum_sync_returns_all_posts(client, fake, kurs, tmp_path):
    setup_fake(fake)
    result = sync_forums(client, kurs, tmp_path, Manifest(tmp_path / "m.json"))
    assert [p.subject for p in result.posts] == ["Termin verschoben", "Folie 12", "Re: Folie 12"]
    assert result.posts[0].is_announcement and not result.posts[1].is_announcement
    assert result.posts[2].text == "Ja, richtig ist minus."
    thread = (tmp_path / result.posts[1].thread_file).read_text(encoding="utf-8")
    assert "Tutor B" in thread and "Vorzeichen" in thread


def test_unchanged_discussions_are_skipped(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest(tmp_path / "m.json")
    sync_forums(client, kurs, tmp_path, manifest)
    fake.calls.clear()
    result = sync_forums(client, kurs, tmp_path, manifest)
    assert result.posts == []
    assert "mod_forum_get_discussion_posts" not in [c[0] for c in fake.calls]


def test_only_new_replies_are_reported(client, fake, kurs, tmp_path):
    setup_fake(fake)
    manifest = Manifest(tmp_path / "m.json")
    sync_forums(client, kurs, tmp_path, manifest)

    POSTS["600"].append(
        {
            "id": 4,
            "subject": "Re: Folie 12",
            "message": "Danke!",
            "author": {"fullname": "Student A"},
            "timecreated": 1760000300,
        }
    )
    fake.responses["mod_forum_get_forum_discussions"] = lambda f: (
        {"discussions": [{"id": 2, "discussion": 600, "name": "Folie 12", "timemodified": 30}]}
        if f["forumid"] == "101"
        else discussions(f)
    )
    try:
        result = sync_forums(client, kurs, tmp_path, manifest)
    finally:
        POSTS["600"].pop()
    assert [p.text for p in result.posts] == ["Danke!"]


def test_broken_forum_does_not_stop_others(client, fake, kurs, tmp_path):
    setup_fake(fake)

    def flaky(form):
        if form["forumid"] == "100":
            return {"exception": "x", "errorcode": "nopermissions", "message": "nein"}
        return discussions(form)

    fake.responses["mod_forum_get_forum_discussions"] = flaky
    result = sync_forums(client, kurs, tmp_path, Manifest(tmp_path / "m.json"))
    assert len(result.posts) == 2 and len(result.errors) == 1
