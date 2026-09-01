from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from .api import CheckpointDApi


_STATIC_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


class CheckpointDLocalDemoApplication:
    """Serve the fixed local UI beside the fail-closed JSON API.

    This is a loopback development surface, not a production web server. Only
    three known assets are served, so request paths cannot traverse the workspace.
    """

    def __init__(self, api: CheckpointDApi, ui_directory: str | Path) -> None:
        self.api = api
        self.ui_directory = Path(ui_directory).resolve()
        missing = [
            filename
            for filename, _ in _STATIC_ASSETS.values()
            if not (self.ui_directory / filename).is_file()
        ]
        if missing:
            raise FileNotFoundError(f"missing Checkpoint D UI assets: {sorted(set(missing))}")

    @staticmethod
    def _respond(
        start_response,
        status: str,
        body: bytes,
        *,
        content_type: str,
        head_only: bool = False,
    ) -> Iterable[bytes]:
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            (
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'",
            ),
        ]
        start_response(status, headers)
        return [b"" if head_only else body]

    def __call__(self, environ: Mapping[str, object], start_response) -> Iterable[bytes]:
        path = urlsplit(str(environ.get("PATH_INFO", "/"))).path
        asset = _STATIC_ASSETS.get(path)
        if asset is None:
            return self.api(environ, start_response)

        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        if method not in {"GET", "HEAD"}:
            return self._respond(
                start_response,
                "405 Method Not Allowed",
                b"method not allowed",
                content_type="text/plain; charset=utf-8",
                head_only=method == "HEAD",
            )
        filename, content_type = asset
        body = (self.ui_directory / filename).read_bytes()
        return self._respond(
            start_response,
            "200 OK",
            body,
            content_type=content_type,
            head_only=method == "HEAD",
        )
