"""Real loopback HTTP tests; all credentials and upstream responses are fixtures."""
import contextlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPEC = importlib.util.spec_from_file_location(
    "ai_http_bridge", Path(__file__).resolve().parents[1] / "tools" / "ai_http_bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class FakeUpstream(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.received.append((self.path, dict(self.headers), json.loads(body)))
        self.send_response(self.server.reply_status)
        self.send_header("Content-Length", str(len(self.server.reply_body)))
        self.end_headers()
        self.wfile.write(self.server.reply_body)


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        self.upstream.received = []
        self.upstream.reply_status = 200
        self.upstream.reply_body = b'{"choices":[{"message":{"content":"fixture result"}}]}'
        self.local = bridge.create_server(port=0)
        self.threads = []
        for server in (self.upstream, self.local):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.base_url = "http://127.0.0.1:%d" % self.upstream.server_port

    def tearDown(self):
        for server in (self.local, self.upstream):
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join(timeout=2)

    def request(self, payload=None, path="/complete", method="POST", raw=None):
        body = (raw if raw is not None else json.dumps(payload).encode("utf-8")) if method == "POST" else None
        connection = http.client.HTTPConnection("127.0.0.1", self.local.server_port, timeout=3)
        try:
            connection.request(method, path, body=body)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def payload(self):
        return {"base_url": self.base_url, "api_key": "fixture-key",
                "model": "fixture-model", "messages": [{"role": "user", "content": "hello"}],
                "temperature": 0.2, "max_tokens": 160,
                "response_format": {"type": "json_object"}}

    def test_real_forwarding_and_endpoint_normalization(self):
        for suffix, expected in (("", "/v1/chat/completions"),
                                 ("/", "/v1/chat/completions"),
                                 ("/v1/", "/v1/chat/completions"),
                                 ("/v1/chat/completions", "/v1/chat/completions"),
                                 ("/custom/v2", "/custom/v2/chat/completions")):
            with self.subTest(suffix=suffix):
                payload = self.payload()
                payload["base_url"] += suffix
                payload["unrecognized"] = "not forwarded"
                status, body = self.request(payload)
                self.assertEqual(status, 200)
                self.assertEqual(body, self.upstream.reply_body)
                path, headers, forwarded = self.upstream.received[-1]
                self.assertEqual(path, expected)
                self.assertEqual(headers["Authorization"], "Bearer fixture-key")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(forwarded, {key: value for key, value in self.payload().items()
                                           if key not in ("base_url", "api_key")})

    def test_upstream_error_does_not_expose_body_or_key_or_logs(self):
        self.upstream.reply_status = 401
        self.upstream.reply_body = b'{"secret":"fixture-key upstream private detail"}'
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status, body = self.request(self.payload())
        self.assertEqual(status, 502)
        self.assertIn(b"HTTP 401", body)
        self.assertNotIn(b"fixture-key", body)
        self.assertNotIn(b"private detail", body)
        self.assertEqual(output.getvalue(), "")

    def test_non_json_and_non_object_responses_are_sanitized(self):
        for response in (b"fixture-key private error", b"[]"):
            with self.subTest(response=response):
                self.upstream.reply_body = response
                status, body = self.request(self.payload())
                self.assertEqual(status, 502)
                self.assertEqual(json.loads(body)["error"]["message"], "upstream returned invalid JSON")

    def test_health_and_routes(self):
        self.assertEqual(self.request(path="/health", method="GET"), (200, b'{"ok":true}'))
        status, _ = self.request(path="/other", method="GET")
        self.assertEqual(status, 404)

    def test_invalid_requests_and_size_limit_never_reach_upstream(self):
        for raw in (b"not JSON", b"[]", b"{}"):
            with self.subTest(length=len(raw)):
                status, _ = self.request(raw=raw)
                self.assertEqual(status, 400)
        # The bridge rejects the declared size before reading a body. Sending only
        # headers avoids a Windows TCP reset while a large body is still in flight.
        connection = http.client.HTTPConnection("127.0.0.1", self.local.server_port, timeout=3)
        try:
            connection.putrequest("POST", "/complete")
            connection.putheader("Content-Length", str(bridge.MAX_INPUT_BYTES + 1))
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            self.assertIn("at most 1 MiB", json.loads(response.read())["error"]["message"])
        finally:
            connection.close()
        payload = self.payload()
        payload["api_key"] = "fixture-key\r\nInjected: value"
        self.assertEqual(self.request(payload)[0], 400)
        payload = self.payload()
        payload["base_url"] = "file:///private"
        self.assertEqual(self.request(payload)[0], 400)
        self.assertEqual(self.upstream.received, [])

    def test_redirects_are_not_followed(self):
        self.upstream.reply_status = 302
        self.assertEqual(self.request(self.payload())[0], 502)
        self.assertEqual(len(self.upstream.received), 1)

    def test_non_loopback_bind_is_refused(self):
        for host in ("0.0.0.0", "192.0.2.1", "localhost", "::"):
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "loopback"):
                bridge.create_server(host, 0)

    def test_upstream_connection_failure_is_sanitized(self):
        # Reserve then release an ephemeral port to exercise the real connection error.
        unused = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstream)
        port = unused.server_port
        unused.server_close()
        payload = self.payload()
        payload["base_url"] = "http://127.0.0.1:%d" % port
        status, body = self.request(payload)
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(body)["error"]["message"], "upstream connection failed")


if __name__ == "__main__":
    unittest.main()
