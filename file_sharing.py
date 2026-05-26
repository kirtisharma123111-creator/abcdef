#!/usr/bin/env python3
"""Share one local file over HTTP."""

from __future__ import annotations

import argparse
import html
import mimetypes
import shutil
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse


class SingleFileSharingHandler(BaseHTTPRequestHandler):
    """HTTP handler that exposes exactly one file."""

    server_version = "SingleFileSharingHTTP/1.0"

    def __init__(
        self,
        *args: object,
        shared_file: Path,
        download_name: str | None = None,
        **kwargs: object,
    ) -> None:
        self.shared_file = shared_file
        self.download_name = download_name or shared_file.name
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_landing_page()
            return
        if path == "/download":
            self._send_file()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Only one file is shared")

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path == "/download":
            self._send_file_headers()
            return
        if path == "/":
            self._send_landing_page(write_body=False)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Only one file is shared")

    def do_POST(self) -> None:
        self.send_error(HTTPStatus.METHOD_NOT_ALLOWED, "Uploads are not supported")

    def _send_landing_page(self, write_body: bool = True) -> None:
        stats = self.shared_file.stat()
        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Share File</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 720px; }}
    .card {{ border: 1px solid #ddd; border-radius: 0.5rem; padding: 1rem; }}
    .muted {{ color: #666; }}
    a.button {{
      display: inline-block;
      margin-top: 1rem;
      padding: 0.6rem 1rem;
      border-radius: 0.4rem;
      background: #0b5fff;
      color: white;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <h1>Shared File</h1>
  <div class="card">
    <h2>{html.escape(self.download_name)}</h2>
    <p class="muted">Size: {html.escape(self._format_size(stats.st_size))}</p>
    <p class="muted">Modified: {html.escape(self.date_time_string(stats.st_mtime))}</p>
    <a class="button" href="/download">Download file</a>
  </div>
</body>
</html>
"""
        encoded = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if write_body:
            self.wfile.write(encoded)

    def _send_file_headers(self) -> None:
        stats = self.shared_file.stat()
        content_type = mimetypes.guess_type(self.download_name)[0] or "application/octet-stream"
        quoted_name = quote(self.download_name)

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(stats.st_size))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{self._header_filename(self.download_name)}\"; filename*=UTF-8''{quoted_name}",
        )
        self.end_headers()

    def _send_file(self) -> None:
        self._send_file_headers()
        with self.shared_file.open("rb") as file_handle:
            shutil.copyfileobj(file_handle, self.wfile)

    @staticmethod
    def _header_filename(filename: str) -> str:
        ascii_name = filename.encode("ascii", "replace").decode("ascii")
        return ascii_name.replace("\\", "\\\\").replace('"', r"\"")

    @staticmethod
    def _format_size(size: int) -> str:
        units = ("B", "KB", "MB", "GB", "TB")
        value = float(size)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                return f"{value:.1f} {unit}" if unit != "B" else f"{size} B"
            value /= 1024
        return f"{size} B"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Share one file over HTTP.")
    parser.add_argument("file", help="Path to the single file to share.")
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind to.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    parser.add_argument(
        "--name",
        help="Optional download name to show to visitors instead of the file's current name.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shared_file = Path(args.file).expanduser().resolve()
    if not shared_file.is_file():
        raise SystemExit(f"File not found: {shared_file}")

    handler = partial(
        SingleFileSharingHandler,
        shared_file=shared_file,
        download_name=args.name,
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    host = args.host if args.host != "0.0.0.0" else "localhost"

    print(f"Sharing {shared_file} at http://{host}:{args.port}/")
    print("Only this file is available. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping file sharing server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
