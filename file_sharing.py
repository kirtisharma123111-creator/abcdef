#!/usr/bin/env python3
"""Simple file sharing server.

Run this script to share files from a local directory over HTTP. It also
provides a browser upload form unless uploads are disabled.
"""

from __future__ import annotations

import argparse
import html
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlparse


class FileSharingHandler(SimpleHTTPRequestHandler):
    """HTTP handler that lists, downloads, and uploads files."""

    server_version = "FileSharingHTTP/1.0"

    def __init__(
        self,
        *args: object,
        directory: str | None = None,
        uploads_enabled: bool = True,
        max_upload_size: int = 50 * 1024 * 1024,
        **kwargs: object,
    ) -> None:
        self.uploads_enabled = uploads_enabled
        self.max_upload_size = max_upload_size
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send_directory_page()
            return

        super().do_GET()

    def do_POST(self) -> None:
        if not self.uploads_enabled:
            self.send_error(HTTPStatus.FORBIDDEN, "Uploads are disabled")
            return

        path = urlparse(self.path).path
        if path != "/upload":
            self.send_error(HTTPStatus.NOT_FOUND, "Upload endpoint not found")
            return

        try:
            saved_name = self._save_uploaded_file()
        except ValueError as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", f"/?uploaded={quote(saved_name)}")
        self.end_headers()

    def _send_directory_page(self) -> None:
        share_dir = Path(self.directory).resolve()
        entries = sorted(share_dir.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        rows = "\n".join(self._format_entry(entry, share_dir) for entry in entries)
        upload_form = self._upload_form() if self.uploads_enabled else "<p>Uploads are disabled.</p>"

        page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>File Sharing</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; max-width: 900px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border-bottom: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    form {{ margin: 1rem 0; padding: 1rem; border: 1px solid #ddd; border-radius: 0.5rem; }}
    .muted {{ color: #666; }}
  </style>
</head>
<body>
  <h1>File Sharing</h1>
  <p class="muted">Serving: {html.escape(str(share_dir))}</p>
  {upload_form}
  <h2>Available files</h2>
  <table>
    <thead><tr><th>Name</th><th>Size</th><th>Modified</th></tr></thead>
    <tbody>
      {rows or '<tr><td colspan="3">No files yet.</td></tr>'}
    </tbody>
  </table>
</body>
</html>
"""
        encoded = page.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _format_entry(self, entry: Path, root: Path) -> str:
        stats = entry.stat()
        name = entry.name + ("/" if entry.is_dir() else "")
        relative_path = entry.relative_to(root).as_posix()
        href = "/" + quote(relative_path)
        size = "-" if entry.is_dir() else self._format_size(stats.st_size)
        modified = self.date_time_string(stats.st_mtime)

        return (
            "<tr>"
            f'<td><a href="{html.escape(href, quote=True)}">{html.escape(name)}</a></td>'
            f"<td>{html.escape(size)}</td>"
            f"<td>{html.escape(modified)}</td>"
            "</tr>"
        )

    def _upload_form(self) -> str:
        max_mb = self.max_upload_size // (1024 * 1024)
        return f"""<form action="/upload" method="post" enctype="multipart/form-data">
    <label>
      Upload a file:
      <input type="file" name="file" required>
    </label>
    <button type="submit">Upload</button>
    <p class="muted">Maximum upload size: {max_mb} MB</p>
  </form>"""

    def _save_uploaded_file(self) -> str:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            raise ValueError("Missing upload body")
        if content_length > self.max_upload_size:
            raise ValueError("Uploaded file is too large")

        content_type = self.headers.get("Content-Type", "")
        boundary = self._multipart_boundary(content_type)
        if not boundary:
            raise ValueError("Expected multipart/form-data upload")

        body = self.rfile.read(content_length)
        filename, file_bytes = self._extract_file_part(body, boundary)
        safe_name = self._safe_filename(filename)
        destination = self._unique_destination(Path(self.directory) / safe_name)
        destination.write_bytes(file_bytes)
        return destination.name

    @staticmethod
    def _multipart_boundary(content_type: str) -> bytes | None:
        parts = [part.strip() for part in content_type.split(";")]
        if not parts or parts[0].lower() != "multipart/form-data":
            return None

        for part in parts[1:]:
            if part.lower().startswith("boundary="):
                value = part.split("=", 1)[1].strip().strip('"')
                return value.encode("utf-8")
        return None

    @staticmethod
    def _extract_file_part(body: bytes, boundary: bytes) -> tuple[str, bytes]:
        marker = b"--" + boundary
        for raw_part in body.split(marker):
            if raw_part in {b"", b"--", b"--\r\n"}:
                continue
            part = raw_part[2:] if raw_part.startswith(b"\r\n") else raw_part

            headers_blob, separator, content = part.partition(b"\r\n\r\n")
            if not separator:
                continue
            if content.endswith(b"\r\n"):
                content = content[:-2]

            headers = headers_blob.decode("utf-8", errors="replace").split("\r\n")
            disposition = next(
                (line for line in headers if line.lower().startswith("content-disposition:")),
                "",
            )
            if 'name="file"' not in disposition or "filename=" not in disposition:
                continue

            filename = FileSharingHandler._disposition_value(disposition, "filename")
            if not filename:
                raise ValueError("No file selected")
            return filename, content

        raise ValueError("Could not find uploaded file")

    @staticmethod
    def _disposition_value(disposition: str, key: str) -> str | None:
        prefix = f'{key}="'
        start = disposition.find(prefix)
        if start == -1:
            return None

        start += len(prefix)
        end = disposition.find('"', start)
        if end == -1:
            return None
        return disposition[start:end]

    @staticmethod
    def _safe_filename(filename: str) -> str:
        cleaned = filename.replace("\x00", "")
        name = PurePosixPath(unquote(cleaned.replace("\\", "/"))).name
        if not name or name in {".", ".."}:
            raise ValueError("Invalid file name")
        return name

    @staticmethod
    def _unique_destination(path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        counter = 1
        while True:
            candidate = parent / f"{stem}-{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

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
    parser = argparse.ArgumentParser(description="Share files from a directory over HTTP.")
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory to share. Defaults to the current directory.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host/interface to bind to.")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on.")
    parser.add_argument("--no-upload", action="store_true", help="Disable browser uploads.")
    parser.add_argument(
        "--max-upload-mb",
        type=int,
        default=50,
        help="Maximum upload size in megabytes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    share_dir = Path(args.directory).expanduser().resolve()
    share_dir.mkdir(parents=True, exist_ok=True)

    handler = partial(
        FileSharingHandler,
        directory=str(share_dir),
        uploads_enabled=not args.no_upload,
        max_upload_size=args.max_upload_mb * 1024 * 1024,
    )

    server = ThreadingHTTPServer((args.host, args.port), handler)
    host = args.host if args.host != "0.0.0.0" else "localhost"
    print(f"Sharing {share_dir} at http://{host}:{args.port}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping file sharing server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
