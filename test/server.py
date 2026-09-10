"""Local HTTP contract fixture. Only binds loopback and uses fake credentials.

Reads explicit test cases, checks wire requests, and returns complete API-shaped
responses. Fault modes exercise the real HTTP transports, without sending email.
"""
import email.parser
import email.policy
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

cases = json.loads((Path(__file__).parent / "cases.json").read_text())
requests = []
lock = threading.Lock()
SSE = ': heartbeat\r\nid: evt-1\r\nevent: message.received\r\ndata: {"text":\r\ndata: "héllo"}\r\n\r\ndata: second\n\nid: evt-2\nevent: reconnect\ndata: {}\n\ndata: incomplete'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(raw)

    def handle_request(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/__requests":
            with lock:
                snapshot = list(requests)
            return self.respond(200, snapshot)
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        auth = self.headers.get("Authorization", "")
        with lock:
            requests.append({"method": self.command, "path": self.path, "auth": auth})
        if auth.startswith("Bearer error-"):
            status = int(auth.rsplit("-", 1)[1])
            return self.respond(status, {"error": "Fixture rejection", "code": "FIXTURE_ERROR", "payment_required": status == 402}, {"Retry-After": "7", "X-Robotomail-Inbound-Quota": "10/10"})
        if auth == "Bearer redirect":
            return self.respond(307, {"error": "Redirect"}, {"Location": f"http://127.0.0.1:{self.server.server_port}/__unexpected"})
        if auth == "Bearer slow":
            time.sleep(0.3)
        if auth == "Bearer html":
            self.send_response(502); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(b"<html>upstream unavailable</html>"); return
        if auth == "Bearer echo":
            return self.respond(200, {"mailboxes": [], "echo": json.loads(raw or b"null"), "query": parse_qs(parsed.query)})
        if auth not in {"Bearer test-key", "Bearer slow", "Bearer bad-stream"}:
            return self.respond(401, {"error": "Invalid API key"})
        matches = [c for c in cases if c["method"] == self.command and "/v1" + c["request_path"] == parsed.path]
        if not matches:
            return self.respond(404, {"error": "Unexpected route", "path": parsed.path})
        case = matches[0]
        try:
            assert self.headers.get("User-Agent", "").startswith("robotomail-"), "Missing SDK user agent"
            assert parse_qs(parsed.query) == {k: [str(v)] for k, v in case["query"].items()}, "Incorrect query parameters"
            for key, value in case["headers"].items():
                assert self.headers.get(key) == str(value), "Incorrect request header " + key
            if case["upload"]:
                content_type = self.headers.get("Content-Type", "")
                assert content_type.startswith("multipart/form-data; boundary="), "Missing multipart boundary"
                message = email.parser.BytesParser(policy=email.policy.default).parsebytes(("Content-Type: " + content_type + "\r\n\r\n").encode() + raw)
                parts = list(message.iter_parts())
                assert len(parts) == 1, "Expected one attachment"
                assert parts[0].get_param("name", header="content-disposition") == "file", "Wrong upload field"
                assert parts[0].get_filename() == "sample.bin", "Wrong filename"
                assert parts[0].get_content_type() == "application/octet-stream", "Wrong content type"
                assert parts[0].get_payload(decode=True) == b"\x00\xffbinary\r\n", "Binary content changed"
            elif case["body"] is not None:
                assert self.headers.get("Content-Type", "").startswith("application/json"), "Missing JSON content type"
                assert json.loads(raw) == case["body"], "Request JSON differs from the contract case"
            else:
                assert raw in {b"", b"null"}, "Unexpected request body"
        except (AssertionError, ValueError) as error:
            return self.respond(422, {"error": str(error), "operation": case["id"]})
        if case["id"] == "streamEvents":
            self.send_response(200)
            self.send_header("Content-Type", "application/json" if auth == "Bearer bad-stream" else "text/event-stream")
            self.end_headers()
            data = SSE.encode()
            # Split every UTF-8 codepoint and CRLF across writes.
            for byte in data:
                self.wfile.write(bytes([byte])); self.wfile.flush()
            return
        self.respond(case["status"], case["response"], {"X-Robotomail-Inbound-Quota": "2/1000"})

    def safe_handle(self):
        try:
            self.handle_request()
        except (BrokenPipeError, ConnectionResetError):
            pass

    do_GET = do_POST = do_PATCH = do_DELETE = safe_handle


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"http://127.0.0.1:{server.server_port}/v1", flush=True)
    server.serve_forever()
