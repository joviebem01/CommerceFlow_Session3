"""Local HTTP/JSON and gRPC services and their RPC client."""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from delivery_metrics import AbandonedResponseCounter
from wire import JsonCodec


def make_service(
    records, abandoned_responses: AbandonedResponseCounter | None = None
):
    counter = abandoned_responses or AbandonedResponseCounter()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            response_attempted = False
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                req = JsonCodec.decode(body)
                method = req.get("method")
                if method == "GetRegion":
                    state = str(req.get("state", "")).strip()
                    response = next(
                        (
                            dict(region=row[0], transaction_count=row[1], revenue_total=row[2])
                            for row in records
                            if row[0] == state
                        ),
                        {"error": "unknown state"},
                    )
                elif method == "GetSummary":
                    response = dict(
                        regions=len(records),
                        transactions=sum(row[1] for row in records),
                        revenue_total=sum(row[2] for row in records),
                    )
                elif method == "ListRegions":
                    response = {
                        "regions": [
                            dict(region=row[0], transaction_count=row[1], revenue_total=row[2])
                            for row in records
                        ]
                    }
                else:
                    response = {"error": "unsupported method"}
                payload = JsonCodec.encode(response)
                response_attempted = True
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                if response_attempted:
                    counter.record_abandoned()
            except Exception:
                try:
                    self.send_error(500)
                except (OSError, ConnectionError):
                    pass

        def do_GET(self):
            if self.path != "/stream":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                for row in records:
                    self.wfile.write(
                        JsonCodec.encode_line(
                            dict(region=row[0], count=row[1], revenue=row[2])
                        )
                    )
                    self.wfile.flush()
            except (ConnectionError, OSError):
                counter.record_abandoned()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
