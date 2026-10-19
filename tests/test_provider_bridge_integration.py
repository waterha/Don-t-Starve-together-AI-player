"""Exercise the actual Lua 5.1 provider through real loopback bridge HTTP."""
import http.client
import json
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime, lua_type
from test_http_bridge import BridgeTest

ROOT = Path(__file__).resolve().parents[1]


class ProviderBridgeIntegrationTest(unittest.TestCase):
    setUp = BridgeTest.setUp
    tearDown = BridgeTest.tearDown

    def run_provider(self):
        lua = LuaRuntime(unpack_returned_tuples=True)

        def from_lua(value):
            if lua_type(value) != "table":
                return value
            keys = list(value.keys())
            if keys and all(isinstance(key, int) for key in keys):
                return [from_lua(value[index]) for index in range(1, len(keys) + 1)]
            return {key: from_lua(value[key]) for key in keys}

        def to_lua(value):
            if isinstance(value, dict):
                return lua.table_from({key: to_lua(item) for key, item in value.items()})
            if isinstance(value, list):
                return lua.table_from([to_lua(item) for item in value])
            return value

        lua.globals().encode_json = lambda value: json.dumps(from_lua(value))
        lua.globals().decode_json = lambda value: to_lua(json.loads(value))
        lua.execute('package.preload.json = function() return {encode_compliant=encode_json, decode=decode_json} end')
        calls = []

        def query_server(_self, url, callback, method, payload):
            self.assertEqual(url, "http://127.0.0.1:17893/complete")
            self.assertEqual(method, "POST")
            connection = http.client.HTTPConnection("127.0.0.1", self.local.server_port, timeout=3)
            try:
                connection.request(method, "/complete", payload.encode("utf-8"))
                response = connection.getresponse()
                body = response.read().decode("utf-8")
                calls.append(response.status)
                callback(body, response.status == 200, response.status)
            finally:
                connection.close()

        lua.globals().TheSim = lua.table_from({"QueryServer": query_server})
        provider = lua.execute((ROOT / "scripts" / "ai_provider.lua").read_text(encoding="utf-8"))
        instance = provider.new(self.base_url, "fixture-model", "fixture-key")
        results = []
        messages = to_lua([{"role": "user", "content": "choose an action"}])
        instance.Complete(instance, messages, lambda content, error: results.append((content, error)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(results), 1)
        return calls[0], results[0]

    def test_lua_complete_reaches_upstream_and_returns_content(self):
        action = '{"action":"follow"}'
        self.upstream.reply_body = json.dumps({"choices": [{"message": {"content": action}}]}).encode()
        status, result = self.run_provider()
        self.assertEqual(status, 200)
        self.assertEqual(result, (action, None))
        path, headers, payload = self.upstream.received[0]
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer fixture-key")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(payload, {"model": "fixture-model",
                                  "messages": [{"role": "user", "content": "choose an action"}],
                                  "temperature": 0.2, "max_tokens": 160,
                                  "response_format": {"type": "json_object"}})

    def test_multiple_lua_providers_forward_only_their_own_credentials(self):
        lua = LuaRuntime(unpack_returned_tuples=True)

        def from_lua(value):
            if lua_type(value) != "table":
                return value
            keys = list(value.keys())
            if keys and all(isinstance(key, int) for key in keys):
                return [from_lua(value[index]) for index in range(1, len(keys) + 1)]
            return {key: from_lua(value[key]) for key in keys}

        def to_lua(value):
            if isinstance(value, dict):
                return lua.table_from({key: to_lua(item) for key, item in value.items()})
            if isinstance(value, list):
                return lua.table_from([to_lua(item) for item in value])
            return value

        lua.globals().encode_json = lambda value: json.dumps(from_lua(value))
        lua.globals().decode_json = lambda value: to_lua(json.loads(value))
        lua.execute('package.preload.json = function() return {encode_compliant=encode_json, decode=decode_json} end')
        forwarded = []

        def query_server(_self, url, callback, method, body):
            self.assertEqual(url, "http://127.0.0.1:17893/complete")
            connection = http.client.HTTPConnection("127.0.0.1", self.local.server_port, timeout=3)
            try:
                connection.request(method, "/complete", body.encode("utf-8"))
                response = connection.getresponse()
                content = response.read().decode("utf-8")
                callback(content, response.status == 200, response.status)
            finally:
                connection.close()

        lua.globals().TheSim = lua.table_from({"QueryServer": query_server})
        provider = lua.execute((ROOT / "scripts" / "ai_provider.lua").read_text(encoding="utf-8"))
        first = provider.new(self.base_url, "model-one", "slot-one-key", "chat_completions")
        second = provider.new(self.base_url, "model-two", "slot-two-key", "chat_completions")
        messages = to_lua([{"role": "user", "content": "fixture"}])
        for instance in (first, second, first):
            instance.Complete(instance, messages, lambda *_: None)
            forwarded.append(self.upstream.received[-1][1]["Authorization"])
        self.assertEqual(forwarded, ["Bearer slot-one-key", "Bearer slot-two-key", "Bearer slot-one-key"])
        self.assertEqual([entry[2]["model"] for entry in self.upstream.received[-3:]],
                         ["model-one", "model-two", "model-one"])

    def test_lua_complete_receives_sanitized_bridge_error(self):
        self.upstream.reply_status = 401
        self.upstream.reply_body = b'private upstream detail fixture-key'
        status, result = self.run_provider()
        self.assertEqual(status, 502)
        self.assertEqual(result, (None, "upstream returned HTTP 401"))

    def test_success_status_with_api_error_is_sanitized(self):
        self.upstream.reply_body = b'{"error":{"message":"private detail fixture-key"}}'
        status, result = self.run_provider()
        self.assertEqual(status, 502)
        self.assertEqual(result, (None, "upstream reported API error"))

    def test_lua_complete_receives_non_json_upstream_error(self):
        self.upstream.reply_body = b'private upstream detail fixture-key'
        status, result = self.run_provider()
        self.assertEqual(status, 502)
        self.assertEqual(result, (None, "upstream returned invalid JSON"))


del BridgeTest


if __name__ == "__main__":
    unittest.main()
