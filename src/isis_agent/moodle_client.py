"""Dünner, nur lesender Client für die Moodle-REST-API von ISIS."""

import logging
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from .config import Secret

log = logging.getLogger(__name__)

# Der Mobile-App-Token hat volle Kontorechte, deshalb nur lesende Funktionen zulassen.
ALLOWED_FUNCTIONS = frozenset(
    {
        "core_webservice_get_site_info",
        "core_enrol_get_users_courses",
        "core_course_get_contents",
        "mod_forum_get_forums_by_courses",
        "mod_forum_get_forum_discussions",
        "mod_forum_get_discussion_posts",
        "mod_resource_get_resources_by_courses",
        "mod_folder_get_folders_by_courses",
        "mod_url_get_urls_by_courses",
        "mod_page_get_pages_by_courses",
        "mod_assign_get_assignments",
    }
)
REST_PATH = "/webservice/rest/server.php"


class MoodleError(Exception):
    """Fehlerantwort der Moodle-API (kommt als HTTP 200 mit 'exception')."""

    def __init__(self, errorcode: str, message: str) -> None:
        super().__init__(f"{errorcode}: {message}")
        self.errorcode = errorcode
        self.message = message


def mask_token(text: str, token: Secret) -> str:
    value = token.reveal()
    return text.replace(value, "***") if value else text


def flatten_params(params: Mapping[str, Any], prefix: str = "") -> dict[str, str]:
    """Wandelt verschachtelte Parameter in Moodles Form-Notation (a[0][b]=...) um."""
    flat: dict[str, str] = {}
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, Mapping):
            flat.update(flatten_params(value, name))
        elif isinstance(value, list | tuple):
            flat.update(flatten_params(dict(enumerate(value)), name))
        elif isinstance(value, bool):
            flat[name] = "1" if value else "0"
        else:
            flat[name] = str(value)
    return flat


class MoodleClient:
    def __init__(
        self,
        base_url: str,
        token: Secret,
        http: httpx.Client | None = None,
        retries: int = 3,
        backoff: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._host = urlsplit(self.base_url).netloc
        self._token = token
        self._http = http or httpx.Client(timeout=30.0, follow_redirects=True)
        self._retries = retries
        self._backoff = backoff
        self._sleep = sleep

    def __enter__(self) -> "MoodleClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def call(self, wsfunction: str, **params: Any) -> Any:
        if wsfunction not in ALLOWED_FUNCTIONS:
            raise PermissionError(f"Moodle-Funktion '{wsfunction}' ist nicht freigegeben")
        data = {
            "wstoken": self._token.reveal(),
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **flatten_params(params),
        }
        response = self._request("POST", self.base_url + REST_PATH, data=data)
        payload = response.json()
        if isinstance(payload, dict) and "exception" in payload:
            raise MoodleError(str(payload.get("errorcode", "")), str(payload.get("message", "")))
        return payload

    def download(self, fileurl: str, dest: Path) -> int:
        """Lädt eine ISIS-Datei atomar nach dest und gibt die Größe in Bytes zurück."""
        url = self._authorized_file_url(fileurl)
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_name(dest.name + ".part")
        size = 0
        for attempt in range(self._retries + 1):
            try:
                with self._http.stream("GET", url) as response:
                    response.raise_for_status()
                    _reject_error_json(response)
                    size = 0
                    with part.open("wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
                            size += len(chunk)
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                part.unlink(missing_ok=True)
                if not self._should_retry(exc, attempt):
                    raise RuntimeError(self._describe(exc)) from None
                self._sleep(self._backoff * 2**attempt)
        os.replace(part, dest)
        return size

    def _authorized_file_url(self, fileurl: str) -> str:
        parts = urlsplit(fileurl)
        if parts.scheme != "https" or parts.netloc != self._host:
            # Token darf nie an fremde Hosts gehen.
            raise PermissionError(f"Download nur von {self._host} erlaubt: {parts.netloc}")
        path = parts.path
        if path.startswith("/pluginfile.php/"):
            path = "/webservice" + path
        query = [(k, v) for k, v in parse_qsl(parts.query) if k != "token"]
        query.append(("token", self._token.reveal()))
        return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), ""))

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._retries + 1):
            try:
                response = self._http.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if not self._should_retry(exc, attempt):
                    raise RuntimeError(self._describe(exc)) from None
                log.warning("ISIS-Anfrage fehlgeschlagen, neuer Versuch: %s", self._describe(exc))
                self._sleep(self._backoff * 2**attempt)
        raise AssertionError("unerreichbar")

    def _should_retry(self, exc: Exception, attempt: int) -> bool:
        if attempt >= self._retries:
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code >= 500
        return True

    def _describe(self, exc: Exception) -> str:
        return mask_token(f"{type(exc).__name__}: {exc}", self._token)


def _reject_error_json(response: httpx.Response) -> None:
    """Moodle liefert bei Dateifehlern manchmal JSON statt der Datei."""
    if response.headers.get("content-type", "").startswith("application/json"):
        response.read()
        payload = response.json()
        if isinstance(payload, dict) and ("exception" in payload or "error" in payload):
            raise MoodleError(
                str(payload.get("errorcode", "download")),
                str(payload.get("message") or payload.get("error", "")),
            )
