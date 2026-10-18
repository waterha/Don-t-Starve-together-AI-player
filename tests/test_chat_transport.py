"""Chat seam contract under Lua 5.1, including actual installed DST callback."""
from pathlib import Path
import os
import re
import unittest
import zipfile

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path(os.environ.get('DST_SCRIPTS_ZIP', r'E:\WeGameApps\rail_apps\饥荒：联机版(2000004)\data\databundles\scripts.zip'))


def installed_native_callback():
    with zipfile.ZipFile(ARCHIVE) as archive:
        source = archive.read('scripts/networking.lua').decode('utf-8-sig')
    match = re.search(r'^function Networking_Say\(guid, userid, name, prefab, message, colour, whisper, isemote, user_vanity\).*?^end\s*$', source, re.M | re.S)
    if match is None:
        raise AssertionError('Installed native signature changed')
    return match.group(0)


class ChatTransportTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            TheWorld={ismastersim=true,ismastershard=true}
            MAX_CHAT_INPUT_LENGTH=150
            function string:utf8len()
                local _,count=self:gsub('[^\\128-\\191]','')
                return count
            end
            native_calls,observed,system_calls=0,0,0
            function Networking_Say(...)
                native_calls=native_calls+1
                native_args={n=select('#',...),...}
                return nil,'native-result',nil
            end
            manager={OnChat=function(self,userid,name,message,whisper)
                observed=observed+1
                observed_args={userid,name,message,whisper}
            end}
            TheNet={SystemMessage=function(self,text)
                system_calls=system_calls+1; system_text=text
            end}
        ''')
        self.lua.globals().Chat = self.lua.execute((ROOT / 'scripts/ai_chat.lua').read_text(encoding='utf-8'))

    def test_exact_forwarding_returns_and_idempotency(self):
        self.lua.execute('''
            assert(Chat.Register(manager))
            local wrapper=Networking_Say
            assert(Chat.Register(manager) and Networking_Say==wrapper)
            local colour,vanity={},{}
            local function capture(...) return {n=select('#',...),...} end
            local result=capture(Networking_Say(71,'real-user','Human','wilson','hello',colour,false,false,vanity,nil))
            assert(result.n==3 and result[1]==nil and result[2]=='native-result' and result[3]==nil)
            assert(native_calls==1 and observed==1)
            assert(native_args.n==10 and native_args[1]==71 and native_args[2]=='real-user')
            assert(native_args[5]=='hello' and native_args[6]==colour and native_args[9]==vanity)
            assert(observed_args[1]=='real-user' and observed_args[3]=='hello')
        ''')

    def test_native_error_propagates_and_observer_error_isolated(self):
        self.lua.execute('''
            Networking_Say=function() native_calls=native_calls+1; error('native-failed') end
            Chat.Register(manager)
            local ok,err=pcall(Networking_Say,1,'user','Human','wilson','hello',{},false,false)
            assert(not ok and err:find('native%-failed') and native_calls==1 and observed==0)
        ''')
        self.setUp()
        self.lua.execute('''
            manager.OnChat=function() error('observer-failed') end
            Chat.Register(manager)
            local a,b=Networking_Say(1,'user','Human','wilson','hello',{},false,false)
            assert(a==nil and b=='native-result' and native_calls==1)
        ''')

    def test_privacy_filters_and_client_secondary_guards(self):
        self.lua.execute('''
            Chat.Register(manager)
            Networking_Say(1,'user','Human','wilson','secret',{},true,false)
            Networking_Say(1,'user','Human','wilson','waves',{},false,true)
            Networking_Say(1,'user','Human','wilson',string.rep('a',151),{},false,false)
            TheWorld.ismastersim=false
            Networking_Say(1,'user','Human','wilson','client',{},false,false)
            TheWorld.ismastersim=true; TheWorld.ismastershard=false
            Networking_Say(1,'user','Human','wilson','caves',{},false,false)
            assert(native_calls==5 and observed==0)
        ''')

    def test_system_broadcast_utf8_cleanup_without_identity(self):
        self.lua.execute('''
            assert(Chat.Clean('你好世界',3)=='你好世')
            assert(Chat.Clean('x'..string.char(0)..'y\\n',20)=='x y')
            assert(Chat.Clean(string.char(237,160,128),20)=='')
            assert(Chat.Say({name='伙伴'},'你好'))
            assert(system_calls==1 and system_text=='[AI 伙伴] 你好')
            assert(not Chat.Say({},''))
            TheWorld.ismastersim=false
            assert(not Chat.Say({},'ignored') and system_calls==1)
        ''')

    @unittest.skipUnless(ARCHIVE.is_file(), 'Installed DST scripts.zip unavailable')
    def test_actual_native_callback_contract(self):
        source = installed_native_callback()
        self.lua.execute('''
            bubbles,history,netids=0,0,0
            Ents={[71]={components={talker={Say=function(self,...)
                bubbles=bubbles+1; bubble_args={n=select('#',...),...}
            end}},HasTag=function(self,tag) return false end}}
            TheNet.GetNetIdForUser=function(self,userid) netids=netids+1; return 'net:'..userid end
            ChatHistory={OnSay=function(self,...)
                history=history+1; history_args={n=select('#',...),...}
            end}
            TEXT_FILTER_CTX_CHAT='CHAT'
        ''')
        self.lua.execute(source)
        self.lua.execute('''
            Chat.Register(manager)
            local colour,vanity={},{}
            Networking_Say(71,'host-user','Host','wilson','host says',colour,false,false,vanity)
            assert(observed==1 and bubbles==1 and history==1 and netids==1)
            assert(bubble_args[1]=='host says' and bubble_args[5]==true and bubble_args[6]==colour)
            assert(bubble_args[7]=='CHAT' and bubble_args[8]=='net:host-user')
            assert(history_args.n==10 and history_args[2]=='host-user' and history_args[3]=='net:host-user')
            assert(history_args[6]=='host says' and history_args[10]==vanity)
            Networking_Say(71,'remote-user','Remote','wendy','remote says',colour,false,false,vanity)
            assert(observed==2 and history==2 and bubbles==2)
            Networking_Say(71,'remote-user','Remote','wendy','private',colour,true,false,vanity)
            assert(observed==2 and history==3 and bubbles==3 and history_args[8]==true)
            Networking_Say(71,'remote-user','Remote','wendy','waves',colour,false,true,vanity)
            assert(observed==2 and history==4 and bubbles==3)
            Networking_Say(71,'remote-user','Remote','wendy',string.rep('a',151),colour,false,false,vanity)
            assert(observed==2 and history==4 and bubbles==3 and netids==4)
        ''')


if __name__ == '__main__':
    unittest.main()
