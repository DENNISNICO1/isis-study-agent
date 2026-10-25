import httpx
import pytest

from isis_agent.config import Secret
from isis_agent.moodle_client import MoodleClient, MoodleError, flatten_params, mask_token

from .conftest import BASE, TOKEN


def test_flatten_params():
    assert flatten_params({"courseids": [3, 4], "opt": {"a": True}, "x": 1}) == {
        "courseids[0]": "3",
        "courseids[1]": "4",
        "opt[a]": "1",
        "x": "1",
    }


def test_call_sends_function_and_params(client, fake):
    fake.responses["core_course_get_contents"] = []
    assert client.call("core_course_get_contents", courseid=7) == []
    fn, form = fake.calls[0]
    assert fn == "core_course_get_contents"
    assert form["courseid"] == "7" and form["moodlewsrestformat"] == "json"


def test_write_functions_are_blocked(client, fake):
    with pytest.raises(PermissionError):
        client.call("mod_forum_add_discussion_post", postid=1)
    assert fake.calls == []


def test_moodle_exception_raises(client, fake):
    fake.responses["core_webservice_get_site_info"] = {
        "exception": "moodle_exception",
        "errorcode": "invalidtoken",
        "message": "Ungültiger Token",
    }
    with pytest.raises(MoodleError) as info:
        client.call("core_webservice_get_site_info")
    assert info.value.errorcode == "invalidtoken"


def test_retries_on_server_error_then_succeeds():
    attempts = []

    def handler(request):
        attempts.append(1)
        if len(attempts) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = MoodleClient(
        BASE,
        Secret(TOKEN),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda s: None,
    )
    assert client.call("core_webservice_get_site_info") == {"ok": True}
    assert len(attempts) == 3


def test_network_error_is_retried_and_token_is_masked(tmp_path):
    attempts = []

    def handler(request):
        attempts.append(str(request.url))
        raise httpx.ConnectError(f"kaputt {request.url}")

    client = MoodleClient(
        BASE,
        Secret(TOKEN),
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        retries=1,
        sleep=lambda s: None,
    )
    with pytest.raises(RuntimeError) as info:
        client.download(f"{BASE}/webservice/pluginfile.php/1/a.pdf", tmp_path / "x")
    assert TOKEN not in str(info.value)
    assert len(attempts) == 2


def test_download_adds_token_and_rewrites_pluginfile(client, fake, tmp_path):
    fake.files["/webservice/pluginfile.php/1/a.pdf"] = b"PDF"
    size = client.download(f"{BASE}/pluginfile.php/1/a.pdf?forcedownload=1", tmp_path / "a.pdf")
    assert size == 3 and (tmp_path / "a.pdf").read_bytes() == b"PDF"
    assert not (tmp_path / "a.pdf.part").exists()


def test_download_refuses_foreign_host(client, tmp_path):
    with pytest.raises(PermissionError):
        client.download("https://evil.example/pluginfile.php/1/a.pdf", tmp_path / "a.pdf")


def test_mask_token():
    assert mask_token(f"url?token={TOKEN}", Secret(TOKEN)) == "url?token=***"
