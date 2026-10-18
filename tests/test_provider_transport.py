"""Use the native four-argument HTTP seam and carry auth only to localhost."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class ProviderTransportTest(unittest.TestCase):
    def runtime(self):
        lua = LuaRuntime()
        lua.execute('''
            package.preload.json = function() return {
                encode=function(value) encoded=value; return "json-payload" end,
                decode=function(value)
                    if value=="success" then return {choices={{message={content='{"action":"follow"}'}}}} end
                    if value=="bridge-error" then return {error="upstream HTTP 401"} end
                    error("invalid JSON")
                end,
            } end
            calls=0
            TheSim={QueryServer=function(self,url,callback,method,data,...)
                calls=calls+1
                assert(select('#',...)==0,"native HTTP API does not accept a headers table")
                assert(url=="http://127.0.0.1:17893/complete","send only to loopback bridge")
                assert(method=="POST" and data=="json-payload")
                callback(reply or "success", http_success~=false, http_status or 200)
            end}
            function done(content,err) result=content; failure=err; completed=(completed or 0)+1 end
        ''')
        lua.globals().Provider = lua.execute((ROOT / 'scripts/ai_provider.lua').read_text(encoding='utf-8'))
        return lua

    def test_native_http_signature_and_bridge_payload(self):
        lua = self.runtime()
        lua.execute('''
            local p=Provider.new("https://example.invalid", "fixture-model", "fixture-key")
            p:Complete({{role="user",content="follow"}},done)
            assert(result=='{"action":"follow"}',failure)
            assert(completed==1 and calls==1)
            assert(encoded.base_url=="https://example.invalid" and encoded.api_key=="fixture-key")
            assert(encoded.model=="fixture-model" and encoded.messages[1].content=="follow")
        ''')

    def test_bridge_failure_is_reported_once(self):
        lua = self.runtime()
        lua.execute('''
            reply="bridge-error"; http_success=false; http_status=502
            Provider.new(nil,nil,"fixture-key"):Complete({},done)
            assert(result==nil and failure=="upstream HTTP 401")
            assert(completed==1)
        ''')

    def test_missing_key_does_not_send_request(self):
        lua = self.runtime()
        lua.execute('Provider.new(nil,nil,""):Complete({},done); assert(calls==0 and result==nil and failure=="missing API key")')


if __name__ == '__main__':
    unittest.main()
