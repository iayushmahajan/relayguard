"""Local RelayGuard downstream demo receiver.

This server is intentionally separate from the production backend. It accepts
delivery POSTs from RelayGuard and logs only safe request metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9000
SLOW_DELAY_SECONDS = 15


class DemoReceiverHandler(BaseHTTPRequestHandler):
    server_version = "RelayGuardDemoReceiver/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def do_POST(self) -> None:
        metadata = self._safe_request_metadata()
        print(json.dumps(metadata, sort_keys=True), flush=True)

        if self.path == "/success":
            self._send_json(HTTPStatus.OK, {"status": "accepted"})
            return
        if self.path == "/fail":
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "retryable_failure"},
            )
            return
        if self.path == "/reject":
            self._send_json(HTTPStatus.BAD_REQUEST, {"status": "rejected"})
            return
        if self.path == "/slow":
            time.sleep(SLOW_DELAY_SECONDS)
            self._send_json(HTTPStatus.OK, {"status": "slow_success"})
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"detail": "Not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _safe_request_metadata(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b""
        return {
            "body_sha256": hashlib.sha256(body).hexdigest() if body else None,
            "client_ip": self.client_address[0],
            "content_length": content_length,
            "content_type": self.headers.get("Content-Type"),
            "method": self.command,
            "path": self.path,
            "user_agent": self.headers.get("User-Agent"),
        }

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the RelayGuard local downstream demo receiver.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", default=DEFAULT_PORT, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DemoReceiverHandler)
    print(
        f"RelayGuard demo receiver listening on http://{args.host}:{args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping RelayGuard demo receiver.", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
