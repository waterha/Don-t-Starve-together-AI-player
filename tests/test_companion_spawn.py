"""Bot lifecycle: list registration -> independent selection -> entry, without fake clients."""
import json
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class BotLifecycleTest(unittest.TestCase):
    def runtime(self, primary=True, count=1, existing_human=False):
        lua = LuaRuntime()
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
        lua.globals().Manager = lua.execute((ROOT / 'scripts/ai_player_manager.lua').read_text(encoding='utf-8'))
        lua.execute('manager=Manager.new(function(name) return config[name] end); manager:Start()')
        return lua

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
