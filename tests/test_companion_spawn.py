"""Bot lifecycle: list registration -> independent selection -> entry, without fake clients."""
import json
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class BotLifecycleTest(unittest.TestCase):
    def runtime(self, primary=True, count=1, existing_human=False):
        lua = LuaRuntime()
        lua.globals().package.path = str(ROOT / 'scripts' / '?.lua').replace('\\', '/') + ';' + lua.globals().package.path
        def table(value):
            if isinstance(value, dict):
                return lua.table_from({k: table(v) for k, v in value.items()})
            if isinstance(value, list):
                return lua.table_from([table(v) for v in value])
            return value
        lua.globals().decode_json = lambda content: table(json.loads(content))
        lua.execute('''
            clock, tasks, periodics, requests, snapshots, spawned = 0, {}, {}, {}, {}, {}
            function GetTime() return clock end
            package.preload.json = function() return {decode=decode_json, encode=function() return "observation" end} end
            package.preload.ai_survival = function() return {Observe=function() return {} end, Tick=function() return false end, Apply=function() return false end} end
            package.preload.ai_players_roster = function() return {Publish=function(records)
                local copy={}
                for i,r in ipairs(records) do copy[i]={index=r.index,status=r.status,character=r.character,name=r.name} end
                snapshots[#snapshots+1]=copy
            end} end
            package.preload.ai_provider = function() return {new=function(base,model,key)
                return {Complete=function(self,messages,callback)
                    requests[#requests+1]={messages=messages,callback=callback,key=key,base=base,model=model}
                end}
            end} end
            config={ai_count=1, ai_1_api_key="fixture-key", ai_2_api_key="fixture-key", ai_3_api_key="fixture-key", ai_4_api_key="fixture-key", ai_5_api_key="fixture-key"}
            AllPlayers={}
            function schedule(delay,callback)
                local task={at=clock+delay,cancelled=false,callback=callback}
                function task:Cancel() self.cancelled=true end
                tasks[#tasks+1]=task
                return task
            end
            function advance(seconds)
                local deadline=clock+seconds
                for guard=1,1000 do
                    local idx,nexttask
                    for i,t in ipairs(tasks) do
                        if not t.cancelled and t.at<=deadline and (not nexttask or t.at<nexttask.at) then idx,nexttask=i,t end
                    end
                    if not nexttask then clock=deadline; return end
                    table.remove(tasks,idx); clock=nexttask.at; nexttask.callback()
                end
                error("task loop")
            end
            TheWorld={ismastersim=true,ismastershard=true,state={phase="day"},
                ListenForEvent=function(self,event,fn) if event=="ms_playerjoined" then joined=fn end end,
                DoTaskInTime=function(self,delay,fn) return schedule(delay,fn) end,
                DoPeriodicTask=function(self,delay,fn) periodics[delay]=fn end}
            function entity(x,z)
                local e={components={},tags={},Transform={},listeners={},valid=true}
                function e:IsValid() return self.valid end
                function e:HasTag(tag) return self.tags[tag] or false end
                function e:AddTag(tag) self.tags[tag]=true end
                function e.Transform:GetWorldPosition() return x,0,z end
                function e.Transform:SetPosition(px,py,pz) x,z=px,pz end
                function e:DoTaskInTime(delay,fn) return schedule(delay,function() fn(self) end) end
                function e:ListenForEvent(event,fn) self.listeners[event]=fn end
                e.components.named={SetName=function(self,value) self.value=value end}
                e.components.talker={Say=function() end}
                e.components.locomotor={GoToEntity=function() end,GoToPoint=function() end,Stop=function() end}
                return e
            end
            function SpawnPrefab(prefab)
                local e=entity(0,0); e.userid=""; e.prefab=prefab; e.GUID=100+#spawned
                spawned[#spawned+1]=e; AllPlayers[#AllPlayers+1]=e
                schedule(0,function() if joined then joined(TheWorld,e) end end)
                return e
            end
            function human(x,z)
                local e=entity(x,z); e.userid="fixture-human"
                AllPlayers[#AllPlayers+1]=e; return e
            end
        ''')
        lua.globals().TheWorld.ismastershard = primary
        lua.globals().config.ai_count = count
        if existing_human:
            lua.execute('human(120,240)')
        roster = lua.execute((ROOT / 'scripts/ai_players_roster.lua').read_text(encoding='utf-8'))
        lua.eval('require("ai_players_roster")').CleanName = roster.CleanName
        lua.eval('require("ai_players_roster")').SetName = roster.SetName
        lua.globals().Manager = lua.execute((ROOT / 'scripts/ai_player_manager.lua').read_text(encoding='utf-8'))
        lua.execute('manager=Manager.new(function(name) return config[name] end); manager:Start()')
        return lua

    def test_selection_diagnostics_distinguish_failure_without_exposing_values(self):
        cases = (
            (None, 'invalid api_key', 'invalid api_key'),
            (None, 'upstream returned HTTP 401', 'upstream returned HTTP 401'),
            (None, 'private fixture-key', 'model request failed'),
            ('not JSON', None, 'invalid selection JSON'),
            ('{"character":"missing_mod"}', None, 'character not in enabled roster'),
        )
        for content, error, reason in cases:
            with self.subTest(reason=reason):
                lua = self.runtime(existing_human=True)
                lua.execute('logs={}; print=function(value) logs[#logs+1]=value end; advance(2)')
                lua.globals().requests[1].callback(content, error)
                output = '\n'.join(lua.globals().logs.values())
                self.assertIn('character selection failed (' + reason + '); fallback wilson', output)
                self.assertNotIn('fixture-key', output)
        lua = self.runtime(existing_human=True)
        lua.execute('logs={}; print=function(value) logs[#logs+1]=value end; advance(2)')
        lua.globals().requests[1].callback('{"name":"Test","character":"willow"}', None)
        self.assertEqual(lua.globals().spawned[1].prefab, 'willow')
        self.assertIn('model selected character willow', '\n'.join(lua.globals().logs.values()))

    def test_chooses_name_and_registered_mod_character(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            DST_CHARACTERLIST={"wilson","willow","wanda","wonkey"}
            MODCHARACTERLIST={"mod_survivor","mod_survivor","missing_mod"}
            MODCHARACTEREXCEPTIONS_DST={"willow"}
            SEAMLESSSWAP_CHARACTERLIST={"wonkey"}
            Prefabs={wilson={},willow={},wanda={},wonkey={},mod_survivor={}}
            advance(2)
            local prompt=requests[1].messages[1].content
            assert(prompt:find("mod_survivor",1,true) and prompt:find("wanda",1,true))
            assert(not prompt:find("missing_mod",1,true) and not prompt:find("wonkey",1,true))
            requests[1].callback('{"name":"星河","character":"mod_survivor"}',nil)
            assert(spawned[1].prefab=="mod_survivor" and spawned[1].name=="星河")
            assert(spawned[1].components.named.value=="星河")
            assert(manager.slots[1].name=="星河" and snapshots[#snapshots][1].name=="星河")
            assert(spawned[1].userid=="")
        ''')

    def test_bad_name_is_bounded_and_invalid_character_keeps_valid_name(self):
        lua = self.runtime(existing_human=True)
        lua.execute('advance(2)')
        lua.globals().requests[1].callback(json.dumps({"name": "  小雨\n" + "星" * 80, "character": "dragonfly"}), None)
        self.assertEqual(lua.eval('spawned[1].prefab'), 'wilson')
        chosen = lua.eval('spawned[1].name')
        self.assertTrue(chosen.startswith('小雨'))
        self.assertNotIn('\n', chosen)
        self.assertLessEqual(len(chosen), 48)
        self.assertEqual(lua.eval('snapshots[#snapshots][1].name'), chosen)

    def test_mod_spawn_failure_falls_back_without_losing_name(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            MODCHARACTERLIST={"broken_mod"}; Prefabs={wilson={},broken_mod={}}
            local native_spawn=SpawnPrefab
            function SpawnPrefab(prefab)
                if prefab=="broken_mod" then error("fixture mod constructor failed") end
                return native_spawn(prefab)
            end
            advance(2)
            requests[1].callback('{"name":"River","character":"broken_mod"}',nil)
            assert(#spawned==1 and spawned[1].prefab=="wilson" and spawned[1].name=="River")
            assert(snapshots[#snapshots][1].character=="wilson")
        ''')

    def test_removed_unregistered_and_internal_characters_are_rejected(self):
        for character in ('willow', 'missing_mod', 'wonkey', 'dragonfly'):
            with self.subTest(character=character):
                lua = self.runtime(existing_human=True)
                lua.execute('''
                    DST_CHARACTERLIST={"wilson","willow","wonkey"}
                    MODCHARACTERLIST={"missing_mod"}
                    MODCHARACTEREXCEPTIONS_DST={"willow"}
                    SEAMLESSSWAP_CHARACTERLIST={"wonkey"}
                    Prefabs={wilson={},willow={},wonkey={},dragonfly={}}
                    advance(2)
                ''')
                lua.globals().requests[1].callback(json.dumps({"name": "River", "character": character}), None)
                self.assertEqual(lua.eval('spawned[1].prefab'), 'wilson')

    def test_long_mod_id_is_canonicalized_like_native_spawn(self):
        lua = self.runtime(existing_human=True)
        identifier = 'mod_' + 'survivor_' * 6 + 'special-build'
        lua.globals().mod_id = identifier
        lua.execute('''
            DST_CHARACTERLIST={}; MODCHARACTERLIST={string.upper(mod_id)}
            Prefabs={[mod_id]={}}
            advance(2)
            assert(requests[1].messages[1].content:find(mod_id,1,true))
        ''')
        lua.globals().requests[1].callback(json.dumps({'name': 'River', 'character': identifier}), None)
        self.assertEqual(lua.eval('spawned[1].prefab'), identifier)

    def test_no_available_character_does_not_spawn_unregistered_default(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            DST_CHARACTERLIST={"wilson"}; MODCHARACTEREXCEPTIONS_DST={"wilson"}; Prefabs={}
            advance(2)
            requests[1].callback('{"name":"River","character":"wilson"}',nil)
            assert(#spawned==0 and manager.slots[1].status=="dead")
        ''')

    def test_local_reaction_cadence_is_independent_of_slow_model(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            assert(periodics[.25], "local reaction must be checked within 250ms")
            assert(periodics[30], "default API usage must not increase")
            advance(2); requests[1].callback('{"character":"wilson"}',nil)
            advance(1); assert(#requests==2 and spawned[1]._ai_busy)
            local updates=0
            function manager:UpdateLocal(inst) assert(inst==spawned[1]); updates=updates+1 end
            for i=1,4 do periodics[.25]() end
            assert(updates==4 and #requests==2, "local loop waited for model or generated extra API calls")
            config.request_interval=5
            manager:Start()
            assert(periodics[5], "fast model setting was clamped back to 15s")
        ''')

    def test_lists_before_selection_then_enters_chosen_character(self):
        lua = self.runtime()
        lua.execute('''
            advance(5); assert(#spawned==0 and #requests==0)
            owner=human(120,240); joined(TheWorld,owner)
            advance(1)
            assert(#spawned==0 and #requests==0)
            assert(snapshots[#snapshots][1].status=="selecting")
            advance(1); assert(#requests==1)
            requests[1].callback('{"character":"willow"}',nil)
            assert(#spawned==1 and spawned[1].prefab=="willow")
            local x,y,z=spawned[1].Transform:GetWorldPosition()
            assert(math.abs(x-120)<8 and math.abs(z-240)<8)
            assert(spawned[1].userid=="", "bot must not forge a client userid")
            assert(spawned[1]._ai_mode=="autonomous" and not spawned[1].persists)
            assert(snapshots[#snapshots][1].status=="alive" and snapshots[#snapshots][1].character=="willow")
            joined(TheWorld,owner); advance(2)
            assert(#spawned==1, "repeated human or bot join events duplicated bots")
            spawned[1].listeners.death()
            assert(snapshots[#snapshots][1].status=="dead")
        ''')

    def test_existing_save_with_human_already_present_starts_selection(self):
        lua = self.runtime(existing_human=True)
        lua.execute('advance(2); assert(#requests==1 and #spawned==0); requests[1].callback(\'{"character":"wx78"}\',nil); assert(spawned[1].prefab=="wx78")')

    def test_five_bots_choose_independently_with_repeated_keys(self):
        lua = self.runtime(count=5, existing_human=True)
        lua.execute('''
            advance(2); assert(#requests==5 and #spawned==0)
            for i=1,5 do assert(requests[i].key=="fixture-key") end
            requests[3].callback('{"character":"woodie"}',nil)
            requests[1].callback('{"character":"willow"}',nil)
            assert(manager.by_index[3].prefab=="woodie" and manager.by_index[1].prefab=="willow")
            assert(manager.slots[2].status=="selecting")
            assert(#snapshots[#snapshots]==5)
        ''')

    def test_independent_providers_used_for_selection_and_actions(self):
        lua = self.runtime(count=2, existing_human=True)
        lua.execute('''
            config.ai_1_api_base_url="https://relay.example/v1"
            config.ai_1_model="relay-model"
            config.ai_2_api_base_url="https://api.openai.com/v1"
            config.ai_2_model="gpt-4o-mini"
            advance(2)
            assert(#requests==2)
            assert(requests[1].base==config.ai_1_api_base_url and requests[1].model==config.ai_1_model)
            assert(requests[2].base==config.ai_2_api_base_url and requests[2].model==config.ai_2_model)
            requests[1].callback('{"character":"willow"}',nil)
            requests[2].callback('{"character":"wilson"}',nil)
            advance(1)
            assert(#requests==4)
            for i=1,2 do
                assert(requests[i+2].base==requests[i].base and requests[i+2].model==requests[i].model)
                assert(requests[i+2].key==requests[i].key)
            end
        ''')

    def test_blank_settings_keep_legacy_values_without_overriding_explicit_fields(self):
        lua = self.runtime(count=2, existing_human=True)
        lua.execute('''
            config.api_base_url="https://previous.example/v1"
            config.model="previous-model"
            config.ai_1_api_base_url="https://new.example/v1"
            config.ai_1_model=""
            config.ai_2_api_base_url=""
            config.ai_2_model="new-model"
            advance(2)
            assert(requests[1].base=="https://new.example/v1" and requests[1].model=="previous-model")
            assert(requests[2].base=="https://previous.example/v1" and requests[2].model=="new-model")
        ''')

    def test_direct_spawn_uses_own_provider_and_builtin_defaults(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            config.ai_2_api_base_url="https://direct.example/v1"
            config.ai_2_model="direct-model"
            manager:SpawnOne(2,"direct-key",AllPlayers[1],"willow")
            advance(2)
            assert(requests[1].base=="https://direct.example/v1" and requests[1].model=="direct-model")
            assert(requests[1].key=="direct-key")
            assert(requests[2].base=="https://api.openai.com/v1" and requests[2].model=="gpt-4o-mini")
        ''')

    def test_selection_timeout_falls_back_once_and_ignores_late_reply(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            advance(62); assert(#spawned==1 and spawned[1].prefab=="wilson")
            requests[1].callback('{"character":"willow"}',nil)
            assert(#spawned==1 and spawned[1].prefab=="wilson")
        ''')

    def test_invalid_character_uses_safe_default(self):
        lua = self.runtime(existing_human=True)
        lua.execute('advance(2); requests[1].callback(\'{"character":"dragonfly"}\',nil); assert(#spawned==1 and spawned[1].prefab=="wilson")')

    def test_human_disconnect_during_selection_waits_for_reentry(self):
        lua = self.runtime(existing_human=True)
        lua.execute('''
            advance(2); AllPlayers[1].valid=false
            requests[1].callback('{"character":"willow"}',nil)
            assert(#spawned==0)
            owner=human(150,250); joined(TheWorld,owner); advance(2)
            assert(#requests==2); requests[2].callback('{"character":"wx78"}',nil)
            assert(#spawned==1 and spawned[1].prefab=="wx78")
        ''')

    def test_caves_do_not_duplicate_bots(self):
        lua = self.runtime(primary=False, existing_human=True)
        lua.execute('advance(65); assert(#spawned==0 and #requests==0)')

    def test_zero_count_does_not_create_rows_or_requests(self):
        lua = self.runtime(count=0, existing_human=True)
        lua.execute('advance(65); assert(#spawned==0 and #requests==0 and #snapshots==0)')


if __name__ == '__main__':
    unittest.main()
