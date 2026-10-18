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
                self.assertEqual(json.loads(body), json.loads(self.upstream.reply_body))
                path, headers, forwarded = self.upstream.received[-1]
                self.assertEqual(path, expected)
                self.assertEqual(headers["Authorization"], "Bearer fixture-key")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(forwarded, {key: value for key, value in self.payload().items()
                                           if key not in ("base_url", "api_key")})

    def test_responses_forwarding_and_endpoint_normalization(self):
        self.upstream.reply_body = json.dumps({
            "status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": "fixture result"}]}],
        }).encode("utf-8")
        for suffix, expected in (("", "/v1/responses"), ("/", "/v1/responses"),
                                 ("/v1/", "/v1/responses"),
                                 ("/v1/responses", "/v1/responses"),
                                 ("/responses", "/responses"),
                                 ("/custom/v2", "/custom/v2/responses")):
            with self.subTest(suffix=suffix):
                payload = self.payload()
                payload["api_format"] = "responses"
                payload["base_url"] += suffix
                payload["unrecognized"] = "not forwarded"
                status, body = self.request(payload)
                self.assertEqual(status, 200)
                self.assertEqual(json.loads(body), {"choices": [{"message": {
                    "role": "assistant", "content": "fixture result"}}]})
                path, headers, forwarded = self.upstream.received[-1]
                self.assertEqual(path, expected)
                self.assertEqual(headers["Authorization"], "Bearer fixture-key")
                self.assertEqual(headers["Content-Type"], "application/json")
                self.assertEqual(forwarded, {
                    "model": "fixture-model", "input": payload["messages"],
                    "max_output_tokens": 160, "text": {"format": {"type": "json_object"}},
                    "store": False, "stream": False,
                })

    def test_api_format_and_endpoint_mismatches_are_rejected(self):
        for api_format in (None, "", "private-format", [], {}):
            with self.subTest(api_format=api_format):
                payload = self.payload()
                payload["api_format"] = api_format
                status, body = self.request(payload)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body), {"error": {"message": "invalid api_format"}})
        for api_format, suffix in (("responses", "/v1/chat/completions"),
                                   ("chat_completions", "/v1/responses"),
                                   ("responses", "/v1/chat/completions/extra"),
                                   ("chat_completions", "/v1/responses/extra")):
            with self.subTest(api_format=api_format, suffix=suffix):
                payload = self.payload()
                payload.update(api_format=api_format, base_url=self.base_url + suffix)
                status, body = self.request(payload)
                self.assertEqual(status, 400)
                self.assertEqual(json.loads(body), {"error": {"message": "invalid base_url"}})
        self.assertEqual(self.upstream.received, [])

    def test_responses_failures_are_sanitized(self):
        text = {"type": "message", "content": [
            {"type": "output_text", "text": "must not succeed"}]}
        cases = (
            ({"status": "failed", "output": [text], "error": None}, "upstream response failed"),
            ({"status": "incomplete", "output": [text],
              "incomplete_details": {"reason": "fixture-key private detail"}},
             "upstream response incomplete"),
            ({"status": "in_progress", "output": [text]}, "upstream response incomplete"),
            ({"status": "completed", "output": [{"type": "message", "content": [
                {"type": "refusal", "refusal": "fixture-key private detail"},
                {"type": "output_text", "text": "must not succeed"}]}]},
             "upstream response refused"),
            ({"status": "completed", "output": []}, "upstream response contained no output text"),
            ({"status": "completed", "output": [{"type": "reasoning", "content": [
                {"type": "output_text", "text": "fixture-key private detail"}]}]},
             "upstream response contained no output text"),
            ({"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": ""}]}]}, "upstream response contained no output text"),
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for reply, expected in cases:
                with self.subTest(reply=reply):
                    self.upstream.reply_body = json.dumps(reply).encode("utf-8")
                    payload = self.payload()
                    payload["api_format"] = "responses"
                    status, body = self.request(payload)
                    self.assertEqual(status, 502)
                    self.assertEqual(json.loads(body), {"error": {"message": expected}})
        self.assertEqual(output.getvalue(), "")

    def test_malformed_responses_are_sanitized(self):
        for output in (None, 7, {}, [{"type": "message", "content": None}],
                       [{"type": "message", "content": 7}],
                       [{"type": "message", "content": {"text": "fixture-key"}}]):
            with self.subTest(output=output):
                self.upstream.reply_body = json.dumps({
                    "status": "completed", "output": output}).encode("utf-8")
                payload = self.payload()
                payload["api_format"] = "responses"
                status, body = self.request(payload)
                self.assertEqual(status, 502)
                self.assertEqual(json.loads(body), {
                    "error": {"message": "upstream returned invalid JSON"}})

    def test_responses_selects_only_message_text_and_normalizes_unicode_names(self):
        selected = {"name": "\u5c0f\u660e", "character": "wilson"}
        escaped = json.dumps(selected, ensure_ascii=True)
        split = len(escaped) // 2
        self.upstream.reply_body = json.dumps({
            "status": "completed", "output_text": "wrong top-level text",
            "output": [
                {"type": "reasoning", "content": [
                    {"type": "output_text", "text": "wrong reasoning text"}]},
                {"type": "function_call", "text": "wrong tool text"},
                {"type": "message", "content": [
                    {"type": "summary_text", "text": "wrong content type"},
                    {"type": "output_text", "text": escaped[:split]}]},
                {"type": "message", "content": [
                    {"type": "output_text", "text": escaped[split:]}]},
            ],
        }).encode("utf-8")
        payload = self.payload()
        payload["api_format"] = "responses"
        status, body = self.request(payload)
        self.assertEqual(status, 200)
        content = json.loads(body)["choices"][0]["message"]["content"]
        self.assertEqual(json.loads(content), selected)
        self.assertIn(selected["name"].encode("utf-8"), body)
        self.assertNotIn(b"\\u", body)
        self.assertNotIn(b"wrong", body)

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

    def test_invalid_unicode_upstream_response_is_sanitized(self):
        self.upstream.reply_body = b'{"choices":[{"message":{"content":"\\ud800"}}]}'
        status, body = self.request(self.payload())
        self.assertEqual(status, 502)
        self.assertEqual(json.loads(body), {"error": {"message": "upstream returned invalid JSON"}})

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

    def test_invalid_fields_are_specific_without_exposing_values(self):
        cases = (
            ("base_url", "https://private.example:secret-port/private", "invalid base_url"),
            ("api_key", "private-key\r\nInjected: private", "invalid api_key"),
            ("api_key", "private-\u00e9-key", "invalid api_key"),
            ("model", "   ", "invalid model"),
            ("messages", "private-message", "invalid messages"),
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            for field, value, expected in cases:
                with self.subTest(field=field):
                    payload = self.payload()
                    payload[field] = value
                    status, body = self.request(payload)
                    self.assertEqual(status, 400)
                    self.assertEqual(json.loads(body), {"error": {"message": expected}})
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.upstream.received, [])

    def test_surrounding_whitespace_is_removed_before_forwarding(self):
        payload = self.payload()
        for field in ("base_url", "api_key", "model"):
            payload[field] = " \t\r\n" + payload[field] + "\r\n\t "
        status, _ = self.request(payload)
        self.assertEqual(status, 200)
        path, headers, forwarded = self.upstream.received[-1]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer fixture-key")
        self.assertEqual(forwarded["model"], "fixture-model")

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
