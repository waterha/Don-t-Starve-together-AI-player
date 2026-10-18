"""Actual installed DST codec/provider over loopback HTTP; fixture credentials only."""
import http.client
import json
import os
from pathlib import Path
import re
import unittest
import zipfile

from lupa.lua51 import LuaRuntime
from test_http_bridge import BridgeTest

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ZIP = Path(os.environ.get(
    "DST_SCRIPTS_ZIP",
    "E:/WeGameApps/rail_apps/\u9965\u8352\uff1a\u8054\u673a\u7248(2000004)/data/databundles/scripts.zip"))


@unittest.skipUnless(NATIVE_ZIP.is_file(), "installed native scripts.zip unavailable")
class NativeProviderJSONTest(unittest.TestCase):
    setUp = BridgeTest.setUp
    tearDown = BridgeTest.tearDown

    def runtime(self):
        lua = LuaRuntime(unpack_returned_tuples=True)
        with zipfile.ZipFile(NATIVE_ZIP) as archive:
            lua.execute(archive.read("scripts/json.lua").decode("utf-8"))
        self.assertEqual(lua.eval("_VERSION"), "Lua 5.1")
        self.requests = []
        self.results = []
        self.transport_errors = []

        def query_server(_self, *args):
            try:
                self.assertEqual(len(args), 4, "unexpected QueryServer arg5")
                url, callback, method, payload = args
                self.assertEqual(url, "http://127.0.0.1:17893/complete")
                self.assertEqual(method, "POST")
                connection = http.client.HTTPConnection(
                    "127.0.0.1", self.local.server_port, timeout=3)
                try:
                    connection.request(method, "/complete", payload.encode("utf-8"))
                    response = connection.getresponse()
                    body = response.read().decode("utf-8")
                    self.requests.append((response.status, payload, body))
                    callback(body, response.status == 200, response.status)
                finally:
                    connection.close()
            except Exception as error:
                self.transport_errors.append(error)
                raise

        lua.globals().TheSim = lua.table_from({"QueryServer": query_server})
        provider = lua.execute((ROOT / "scripts/ai_provider.lua").read_text(encoding="utf-8"))
        lua.globals().fixture_provider = provider.new(self.base_url, "fixture-model", "fixture-key")
        return lua

    def complete(self, content):
        lua = self.runtime()
        messages = lua.table_from([lua.table_from({"role": "system", "content": content})])
        provider = lua.globals().fixture_provider
        provider.Complete(provider, messages,
                          lambda result, error: self.results.append((result, error)))
        self.assertEqual(self.transport_errors, [])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], 200, self.requests[0][2])
        self.assertEqual(self.results, [("fixture result", None)])
        self.assertEqual(self.upstream.received[-1][2]["messages"][0]["content"], content)

    def test_encoder_return_count_is_one_not_queryserver_arg5(self):
        lua = self.runtime()
        self.assertEqual(lua.eval("select('#', json.encode({x=1}))"), 1)
        self.assertEqual(lua.eval("select('#', json.decode('{}'))"), 2)

    def test_actual_system_prompt_reaches_upstream(self):
        source = (ROOT / "scripts/ai_player_manager.lua").read_text(encoding="utf-8")
        prompt = re.search(r"local SYSTEM_PROMPT = \[\[(.*?)\]\]", source, re.S)
        self.assertIsNotNone(prompt)
        self.complete(prompt.group(1))

    def test_apostrophes_quotes_backslashes_and_chinese(self):
        self.complete("Don't change the human's name: \u5c0f\u660e. \"hello\" C:\\fixture\\name")

    def test_all_ascii_control_characters_round_trip(self):
        self.complete("controls:" + "".join(chr(number) for number in range(32)))

    def test_native_compliant_encoder_does_not_escape_all_controls(self):
        lua = self.runtime()
        for control in ("\x00", "\x08", "\x0c", "\x1f"):
            with self.subTest(control=repr(control)):
                encoded = lua.globals().json.encode_compliant(control)
                with self.assertRaises(json.JSONDecodeError):
                    json.loads(encoded)
        self.assertEqual(json.loads(lua.globals().json.encode_compliant("Don't")), "Don't")

    def selection(self, ensure_ascii, escaped_character=False, api_format="chat_completions"):
        lua = self.runtime()
        lua.globals().fixture_provider.api_format = api_format
        selected_name = "\u5c0f\u660e"
        content = json.dumps({"name": selected_name, "character": "wilson"},
                             ensure_ascii=ensure_ascii)
        if escaped_character:
            content = content.replace('"wilson"', '"\\u0077illow"')
        response = {"choices": [{"message": {"content": content}}]}
        if api_format == "responses":
            response = {"status": "completed", "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": content}]}]}
        self.upstream.reply_body = json.dumps(response, ensure_ascii=ensure_ascii).encode("utf-8")
        source = (ROOT / "scripts/ai_player_manager.lua").read_text(encoding="utf-8")
        begin = source.index("function AIPlayerManager:BeginSelection(index)")
        end = source.index("function AIPlayerManager:EnsureCompanions()", begin)
        # Execute the real selection method, with only game lifecycle dependencies stubbed.
        lua.execute('''
            AIPlayerManager = {}
            function character_choices() return {"wilson", "willow"} end
            function permitted_character(value, choices)
                for _, choice in ipairs(choices) do if value == choice then return value end end
            end
            Roster = {CleanName = function(value, index, fallback) return value or fallback end}
            function find_human() return nil end
            TheWorld = {DoTaskInTime = function() return {Cancel = function() end} end}
        ''')
        lua.execute(source[begin:end])
        lua.execute('''
            fixture_manager = setmetatable({
                slots = {{status="selecting", provider=fixture_provider}},
                PublishRoster = function() end,
            }, {__index=AIPlayerManager})
            fixture_manager:BeginSelection(1)
        ''')
        self.assertEqual(self.transport_errors, [])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0][0], 200, self.requests[0][2])
        forwarded = self.upstream.received[-1][2]
        messages = forwarded["input"] if api_format == "responses" else forwarded["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Allowed character prefabs", messages[0]["content"])
        if api_format == "responses":
            self.assertEqual(self.upstream.received[-1][0], "/v1/responses")
            self.assertEqual(forwarded["max_output_tokens"], 2048)
            self.assertNotIn("messages", forwarded)
            self.assertNotIn("response_format", forwarded)
        slot = lua.globals().fixture_manager.slots[1]
        self.assertEqual(slot.character, "willow" if escaped_character else "wilson")
        self.assertEqual(slot.name, selected_name)

    def test_responses_selection_with_native_codec_and_escaped_character(self):
        self.selection(ensure_ascii=True, escaped_character=True, api_format="responses")

    def test_actual_selection_payload_and_utf8_chinese_response(self):
        self.selection(ensure_ascii=False)

    def test_escaped_character_prefab_is_not_replaced_with_wilson(self):
        self.selection(ensure_ascii=True, escaped_character=True)

    def test_actual_selection_payload_and_escaped_chinese_response(self):
        self.selection(ensure_ascii=True)


del BridgeTest


if __name__ == "__main__":
    unittest.main()
