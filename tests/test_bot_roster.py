"""Replicated pure-mod roster; native status-screen rows never get fake identities."""
import json
from pathlib import Path
import unittest
import zipfile

from lupa.lua51 import LuaRuntime, lua_type

ROOT = Path(__file__).resolve().parents[1]
NATIVE_SCRIPTS = Path(r"E:\WeGameApps\rail_apps\饥荒：联机版(2000004)\data\databundles\scripts.zip")


class BotRosterTest(unittest.TestCase):
    def runtime(self, master=True):
        lua = LuaRuntime(unpack_returned_tuples=True)

        def to_python(value):
            if lua_type(value) != "table":
                return value
            keys = list(value.keys())
            if all(isinstance(key, (int, float)) for key in keys):
                return [to_python(value[index]) for index in range(1, len(keys) + 1)]
            return {key: to_python(item) for key, item in value.items()}

        lua.globals().encode_json = lambda value: json.dumps(to_python(value), ensure_ascii=False)
        lua.globals().decode_json = lambda value: lua.table_from(json.loads(value), recursive=True)
        lua.execute('''
            package.preload.json = function()
                return {encode=encode_json, decode=decode_json}
            end
            prefabs, classes, tasks, writes = {}, {}, {}, 0
            TheWorld = {ismastersim=true}
            function net_string(guid, name, dirty)
                local var = {data="", guid=guid, name=name, dirty=dirty}
                function var:value() return self.data end
                function var:set(value) self.data=value; writes=writes+1 end
                return var
            end
            function new_net(guid)
                return {GUID=guid, DoTaskInTime=function(self, delay, fn) tasks[#tasks+1]=fn end}
            end
            function flush()
                local pending=tasks; tasks={}
                for _,fn in ipairs(pending) do fn() end
            end
            function add_prefab(name, fn) assert(prefabs[name]==nil); prefabs[name]=fn end
            function add_class(name, fn) assert(classes[name]==nil); classes[name]=fn end
            function add_player(fn) assert(player_post_init==nil); player_post_init=fn end
        ''')
        lua.globals().TheWorld.ismastersim = master
        lua.globals().Roster = lua.execute((ROOT / "scripts/ai_players_roster.lua").read_text(encoding="utf-8"))
        lua.execute('Roster.Register(add_prefab,add_class,add_player)')
        return lua

    def attach(self, lua, prefab="forest_network"):
        lua.globals().prefab_name = prefab
        lua.execute('network=new_net(12); prefabs[prefab_name](network); TheWorld.net=network; flush()')

    def test_registration_both_world_networks_and_native_screen_once(self):
        lua = self.runtime()
        lua.execute('''
            Roster.Register(add_prefab,add_class,add_player)
            assert(prefabs.forest_network and prefabs.cave_network)
            assert(classes["screens/playerstatusscreen"])
            assert(classes["screens/redux/playerstatusscreen"]==nil)
        ''')
        self.attach(lua)
        lua.execute('''
            local var=network._ai_players_roster
            assert(var.guid==12 and var.name=="ai_players.roster")
            assert(var.dirty=="ai_players_roster_dirty")
            prefabs.forest_network(network)
            assert(var==network._ai_players_roster)
        ''')

    def test_player_names_replicate_without_replacing_human_names(self):
        server = self.runtime()
        server.execute('''
            player={GUID=99,name="original",components={},listeners={}}
            function player:ListenForEvent(event,fn) self.listeners[event]=fn end
            function player:DoTaskInTime(delay,fn) tasks[#tasks+1]=fn end
            player_post_init(player)
            local var=player._ai_players_name
            player_post_init(player)
            assert(player._ai_players_name==var)
            assert(var.guid==99 and var.name=="ai_players.display_name")
            flush(); assert(player.name=="original" and writes==0)
            assert(Roster.SetName(player,"星河",1))
            assert(var:value()=="星河" and player.name=="星河" and writes==1)
        ''')
        client = self.runtime(master=False)
        client.execute('''
            player={GUID=99,name="human",components={},listeners={}}
            function player:ListenForEvent(event,fn) self.listeners[event]=fn end
            function player:DoTaskInTime(delay,fn) tasks[#tasks+1]=fn end
            player_post_init(player); flush()
            assert(player.name=="human" and writes==0)
            assert(not Roster.SetName(player,"forged",1))
            assert(player.name=="human" and writes==0)
            player._ai_players_name.data="星河"
            player.listeners.ai_players_name_dirty()
            assert(player.name=="星河" and writes==0)
        ''')

    def test_server_pending_publish_and_whitelisted_json_only(self):
        lua = self.runtime()
        lua.execute('''
            assert(Roster.Publish({{index=1,name="Willow bot",status="selecting",character="willow",
                api_key="SECRET", userid="FAKE", config={api_key="SECRET"}, GUID=99}}))
        ''')
        self.attach(lua)
        data = json.loads(lua.globals().network._ai_players_roster.value(lua.globals().network._ai_players_roster))
        self.assertEqual(data, [{"index": 1, "name": "Willow bot", "status": "selecting", "character": "willow", "GUID": 99}])
        lua.execute('''
            local before=writes
            Roster.Publish({{index=1,name="Willow bot",status="selecting",character="willow",GUID=99}})
            assert(writes==before, "unchanged snapshots should not dirty the netvar")
        ''')

    def test_clients_never_publish_or_set_netvar_even_in_caves(self):
        lua = self.runtime(master=False)
        self.attach(lua, "cave_network")
        lua.execute('''
            assert(writes==0)
            assert(not Roster.Publish({{index=1,name="bot",status="alive",character="wilson"}}))
            assert(writes==0)
            network._ai_players_roster.data='[{"index":1,"name":"remote","status":"dead","character":"wendy"}]'
            assert(Roster.GetSlots()[1].status=="dead")
        ''')

    def test_decode_rejects_bad_data_and_sanitizes_public_records(self):
        lua = self.runtime(master=False)
        self.attach(lua)
        for value in ["", "not json", '"not a list"', "null", "7", "x" * 4097]:
            lua.globals().network._ai_players_roster.data = value
            lua.execute('assert(#Roster.GetSlots()==0)')
        payload = [
            {"index": 5, "name": "第五个\n机器人", "status": "dead", "character": "bad/../prefab", "userid": "FAKE", "GUID": -1},
            {"index": 1, "name": "", "status": "selecting", "character": "wilson", "api_key": "SECRET"},
            {"index": 1, "name": "duplicate", "status": "alive", "character": "willow"},
            {"index": 2.5, "name": "fraction", "status": "alive"},
            {"index": 6, "name": "extra", "status": "alive"},
            {"index": 2, "name": "bad status", "status": "unknown"},
        ]
        lua.globals().network._ai_players_roster.data = json.dumps(payload, ensure_ascii=False)
        lua.execute('''
            local slots=Roster.GetSlots()
            assert(#slots==2 and slots[1].index==1 and slots[2].index==5)
            assert(slots[1].name=="Bot 1" and slots[1].api_key==nil)
            assert(slots[2].character=="" and slots[2].GUID==nil and slots[2].userid==nil)
        ''')
        self.assertEqual(lua.eval('Roster.GetSlots()[2].name'), "第五个机器人")

    def test_all_five_slots_and_utf8_names_are_bounded(self):
        lua = self.runtime()
        self.attach(lua)
        lua.globals().long_name = "机器人" * 100
        lua.execute('''
            local slots={}
            for i=5,1,-1 do slots[#slots+1]={index=i,name=long_name,status="alive",character="wilson"} end
            assert(Roster.Publish(slots))
            local decoded=Roster.GetSlots()
            assert(#decoded==5 and decoded[1].index==1 and decoded[5].index==5)
        ''')
        self.assertEqual(lua.eval('Roster.GetSlots()[1].name'), ("机器人" * 100)[:48])

    def screen_runtime(self, native=False):
        lua = self.runtime()
        self.attach(lua)
        lua.execute(WIDGET_MOCKS)
        if native:
            with zipfile.ZipFile(NATIVE_SCRIPTS) as archive:
                source = archive.read("scripts/screens/playerstatusscreen.lua").decode("utf-8")
            lua.globals().StatusScreen = lua.execute(source)
            lua.execute('screen=StatusScreen({userid="human",components={}})')
        else:
            lua.execute('''
                screen={}
                function screen:DoInit(clients)
                    clients=clients or TheNet:GetClientTable()
                    self.numPlayers=#clients
                    if not self.scroll_list then
                        self.player_widgets={}
                        for i=1,6 do self.player_widgets[i]=make_row() end
                        self.scroll_list=make_list(clients,380,370,60,5,native_row,self.player_widgets)
                        self.bgs={}
                    else
                        self.scroll_list:SetList(clients)
                    end
                end
                function screen:OnUpdate(dt)
                    native_updates=native_updates+1
                    local clients=TheNet:GetClientTable()
                    if #clients~=self.numPlayers then self:DoInit(clients) end
                end
            ''')
        lua.execute('classes["screens/playerstatusscreen"](screen); screen:DoInit()')
        return lua

    def check_screen_lifecycle(self, native=False):
        lua = self.screen_runtime(native=native)
        lua.execute('''
            assert(screen.numPlayers==1 and #clients==1)
            assert(#screen.scroll_list.items==1)
            assert(screen.scroll_list.items[1]==clients[1])
            Roster.Publish({{index=1,name="Companion",status="selecting",character=""}})
            screen:OnUpdate(.6)
            assert(#screen.scroll_list.items==2)
            local row=screen.player_widgets[2]
            assert(row.name.text=="[AI] Companion" and row.age.text=="Selecting")
            assert(row.userid==nil and not row.kick.visible and not row.ban.visible)
            assert(not row.viewprofile.visible and not row.mute.visible and not row.useractions.visible)
            assert(not row.adminBadge.visible and row.focus_forward==nil)
            assert(screen.scroll_list.items[1]==clients[1] and #clients==1 and clients[1]._ai_bot==nil)
            assert(screen.numPlayers==1)
            assert(#screen.bgs==2, "native row background must extend to bot rows")
            Roster.Publish({{index=1,name="Companion",status="alive",character="willow",GUID=17}})
            screen:OnUpdate(.6)
            assert(row.age.text=="Alive" and row._ai_character.text=="willow")
            Roster.Publish({{index=1,name="Companion",status="dead",character="willow",GUID=17}})
            screen:OnUpdate(.6)
            assert(row.age.text=="Dead")
            -- A real client takes the widget previously occupied by a bot.
            clients[2]={userid="human2",name="Human Two",prefab="wendy",colour={1,1,1,1}}
            screen:OnUpdate(.6)
            assert(screen.numPlayers==2 and #screen.scroll_list.items==3)
            assert(screen.scroll_list.items[2]==clients[2])
            assert(row.userid=="human2" and row.name.text=="Human Two")
            assert(not row._ai_character.visible and row.age.size==35)
            assert(row.viewprofile.visible, "native real-client controls were not restored")
            assert(#clients==2 and clients[1].userid=="human")
            Roster.Publish({})
            screen:OnUpdate(.6)
            assert(#screen.scroll_list.items==2 and #screen.bgs==2)
        ''')
        if not native:
            lua.execute('assert(native_updates==5 and native_bot_calls==0)')

    def test_widget_lifecycle_selection_alive_dead_and_real_clients_untouched(self):
        self.check_screen_lifecycle()

    @unittest.skipUnless(NATIVE_SCRIPTS.is_file(), "native scripts.zip is not installed")
    def test_actual_native_screen_functions_with_widget_mocks(self):
        self.check_screen_lifecycle(native=True)

    @unittest.skipUnless(NATIVE_SCRIPTS.is_file(), "native scripts.zip is not installed")
    def test_native_dedicated_server_row_is_untouched(self):
        lua = self.screen_runtime(native=True)
        lua.execute('''
            STRINGS.UI.PLAYERSTATUSSCREEN.PERF_HOST_LEVELS={"Good","OK","Bad"}
            TheNet.GetServerIsClientHosted=function() return false end
            clients={{name="Dedicated server",performance=0},clients[1]}
            screen:DoInit()
            Roster.Publish({{index=1,name="Companion",status="alive",character="wendy"}})
            screen:OnUpdate(.6)
            assert(#clients==2 and screen.numPlayers==2 and #screen.scroll_list.items==3)
            assert(screen.scroll_list.items[1]==clients[1] and clients[1].userid==nil)
            assert(screen.players_number.text=="1/6", "bots must not consume native client capacity")
            assert(screen.player_widgets[3].name.text=="[AI] Companion")
            assert(not screen.player_widgets[1].viewprofile.visible)
            Roster.Publish({})
            screen:OnUpdate(.6)
            assert(#screen.scroll_list.items==2 and not screen.player_widgets[3].visible)
        ''')

    def test_native_age_font_and_visibility_restore_after_bot_reuse(self):
        lua = self.screen_runtime()
        lua.execute('''
            local row=screen.player_widgets[2]
            row.age:SetSize(29)
            row.age:Hide()
            Roster.Publish({{index=1,name="Bot",status="selecting",character=""}})
            screen:OnUpdate(.6)
            assert(row.age.visible and row.age.size==25)
            clients[2]={userid="human2",name="Human Two",prefab="wendy"}
            screen:OnUpdate(.6)
            assert(row.age.size==29 and not row.age.visible)
        ''')

    def test_five_bots_scroll_and_reopen_without_duplicates(self):
        lua = self.screen_runtime()
        lua.execute('''
            local slots={}
            for i=1,5 do slots[i]={index=i,name="Bot "..i,status="selecting",character=""} end
            Roster.Publish(slots)
            screen:OnUpdate(.6)
            assert(#screen.scroll_list.items==6 and #screen.bgs==6)
            screen:DoInit()
            assert(#screen.scroll_list.items==6 and #clients==1)
            local updater=screen.scroll_list.updatefn
            classes["screens/playerstatusscreen"](screen)
            assert(updater==screen.scroll_list.updatefn)
            -- Contract of native scrolling: the same static row receives other data.
            local row=screen.player_widgets[1]
            updater(row,screen.scroll_list.items[6],6)
            assert(row.name.text=="[AI] Bot 5" and row.userid==nil)
            updater(row,clients[1],1)
            assert(row.userid=="human" and not row._ai_character.visible)
            updater(row,nil)
            assert(not row.visible)
        ''')


WIDGET_MOCKS = '''
    native_updates,native_bot_calls=0,0
    UIFONT="font"; NEWFONT_OUTLINE="font"; ANCHOR_MIDDLE=0; ANCHOR_RIGHT=1
    SCALEMODE_PROPORTIONAL=1; SCALEMODE_FILLSCREEN=2
    DEFAULT_PLAYER_COLOUR={1,1,1,1}; WHITE=DEFAULT_PLAYER_COLOUR
    COMMAND_RESULT={DENY=1,DISABLED=2}; MOVE_LEFT=1; MOVE_RIGHT=2
    STRINGS={UI={PLAYERSTATUSSCREEN={AGE_PREFIX="Day ",MODSLISTPRE="Mods",PERF_CLIENT_LEVEL_UNKNOWN="Unknown",VIEWPROFILE="Profile",MUTE="Mute",KICK="Kick",BAN="Ban",ADMIN="Admin",USERACTIONS="Actions"},SERVERLISTINGSCREEN={TOGGLE_SERVER_NAME="Name"}}}
    TheFrontEnd={GetIsOfflineMode=function() return true end,GetFadeLevel=function() return 0 end}
    TheInput={EnableDebugToggle=function() end,ControllerAttached=function() return false end}
    ServerPreferences={IsNameAndDescriptionHidden=function() return false end}
    TheWorld.state={cycles=1}
    clients={{userid="human",name="Human",prefab="wilson",colour={1,1,1,1}}}
    TheNet={GetClientTable=function() return clients end,IsOnlineMode=function() return true end,
        IsVoiceActive=function() return false end,
        GetServerGameMode=function() return "survival" end,GetServerClanID=function() return "" end,
        GetServerIsClientHosted=function() return true end,GetServerMaxPlayers=function() return 6 end,
        GetServerDescription=function() return "" end,GetServerName=function() return "Fixture" end,
        GetServerModsEnabled=function() return false end}
    function GetGameModeString() return "Survival" end
    function ClickMouseoverSoundReduction() return 0 end
    function GetTableSize(t) local n=0; for _ in pairs(t) do n=n+1 end; return n end
    local methods={}
    function methods:AddChild(child) return child end
    function methods:Show() self.visible=true end
    function methods:Hide() self.visible=false end
    function methods:IsVisible() return self.visible end
    function methods:Kill() self.killed=true end
    function methods:SetString(text) self.text=text end
    function methods:SetTruncatedString(text) self.text=text end
    function methods:SetSize(size) self.size=size end
    function methods:GetSize() return self.size or 35 end
    function methods:GetRegionSize() return math.min(#(self.text or "")*10,215),35 end
    function methods:SetPosition(x,y,z) self.position={x,y,z} end
    function methods:SetOnClick(fn) self.onclick=fn end
    function methods:Set(...) self.badge={...} end
    function methods:IsAFK() return false end
    function methods:DoPeriodicTask() return {Cancel=function() end} end
    setmetatable(methods, {__index=function(_,key)
        if key:match("^[A-Z]") then return function() end end
    end})
    function widget()
        local w=setmetatable({visible=true,OnGainFocus=function() end}, {__index=methods})
        w.image=setmetatable({inst={widget=w}}, {__index=methods})
        w.image.inst.DisableMute=function() end
        w.image.inst.DoPeriodicTask=methods.DoPeriodicTask
        return w
    end
    function Class(base, ctor)
        local class={_ctor=ctor,_base=base}; class.__index=class
        setmetatable(class,{__index=base,__call=function(c,...)
            local instance=setmetatable({},c); ctor(instance,...); return instance
        end})
        return class
    end
    local WidgetClass=setmetatable({_ctor=function(self) self.visible=true end}, {__index=methods,__call=function() return widget() end})
    package.preload["widgets/screen"]=function() return WidgetClass end
    package.preload["widgets/widget"]=function() return WidgetClass end
    for _,path in ipairs({"widgets/text","widgets/image","widgets/imagebutton","widgets/playerbadge"}) do
        package.preload[path]=function() return widget end
    end
    package.preload.util=function() return {} end
    package.preload["screens/redux/usercommandpickerscreen"]=function() return function() end end
    package.preload["widgets/redux/templates"]=function() return {RankBadge=widget} end
    package.preload.usercommands=function() return {
        CanUserAccessCommand=function() return false end,
        GetUserActions=function() return {} end,
        UserRunCommandResult=function() error("unexpected user command") end,
    } end
    function make_row()
        local row=widget()
        for _,key in ipairs({"name","age","characterBadge","viewprofile","mute","kick","ban","useractions","adminBadge","perf","profileFlair","number","highlight"}) do
            row[key]=widget()
        end
        row.name._align={maxwidth=215,maxchars=36,x=-286}
        return row
    end
    function native_row(row,client,index)
        if not client then row:Hide(); return end
        if client._ai_bot then native_bot_calls=native_bot_calls+1; error("bot entered native updater") end
        row:Show(); row.userid=client.userid; row.name:SetString(client.name)
        row.viewprofile:Show(); row.focus_forward=row.viewprofile
    end
    function make_list(items,width,height,itemheight,padding,updater,rows)
        local list=widget(); list.items=items; list.updatefn=updater; list.widgets_per_view=6
        function list:SetList(data)
            self.items=data
            for i,row in ipairs(rows) do self.updatefn(row,data[i],i) end
        end
        list:SetList(items)
        return list
    end
    package.preload["widgets/scrollablelist"]=function() return make_list end
'''


if __name__ == "__main__":
    unittest.main()
