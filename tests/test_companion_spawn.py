"""World entry lifecycle: companions must appear beside an actual human."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class CompanionSpawnTest(unittest.TestCase):
    def runtime(self, primary=True):
        lua = LuaRuntime()
        lua.execute('''
            package.preload.ai_provider = function()
                return {new=function() return {} end}
            end
            package.preload.json = function() return {} end
            config = {ai_count=1, ai_1_api_key="fixture-key"}
            AllPlayers = {}
            tasks = {}
            function task(callback)
                local t = {cancelled=false}
                function t:Cancel() self.cancelled=true end
                t.run = function() if not t.cancelled then callback() end end
                tasks[#tasks+1] = t
                return t
            end
            function flush()
                local pending = tasks
                tasks = {}
                for _,t in ipairs(pending) do t.run() end
            end
            joined = nil
            TheWorld = {
                ismastersim=true, ismastershard=true,
                ListenForEvent=function(self, event, fn) if event=="ms_playerjoined" then joined=fn end end,
                DoTaskInTime=function(self, delay, fn) return task(fn) end,
                DoPeriodicTask=function(self, delay, fn) tick=fn; return {Cancel=function() end} end,
            }
            spawned = {}
            function entity(x, z)
                local e = {components={}, tags={}, Transform={}}
                function e:IsValid() return true end
                function e:HasTag(tag) return self.tags[tag] or false end
                function e:AddTag(tag) self.tags[tag]=true end
                function e.Transform:GetWorldPosition() return x,0,z end
                function e.Transform:SetPosition(px,py,pz) x,z=px,pz end
                function e:DoTaskInTime(delay,fn) return task(function() fn(self) end) end
                function e:ListenForEvent() end
                e.components.talker={Say=function() end}
                e.components.locomotor={GoToEntity=function() end,GoToPoint=function() end,Stop=function() end}
                return e
            end
            function SpawnPrefab(name)
                local e = entity(0,0)
                e.userid=""
                spawned[#spawned+1]=e
                AllPlayers[#AllPlayers+1]=e
                e:DoTaskInTime(0,function() if joined then joined(TheWorld,e) end end)
                return e
            end
            function human(x,z)
                local e=entity(x,z)
                e.userid="fixture-human"
                AllPlayers[#AllPlayers+1]=e
                return e
            end
        ''')
        lua.globals().TheWorld.ismastershard = primary
        lua.globals().Manager = lua.execute((ROOT / 'scripts/ai_player_manager.lua').read_text(encoding='utf-8'))
        lua.execute('manager=Manager.new(function(name) return config[name] end); manager:Start()')
        return lua

    def test_waits_for_human_and_spawns_near_entry(self):
        lua = self.runtime()
        lua.execute('''
            flush()
            assert(#spawned==0, "companion spawned before a human joined, at world origin")
            local player=human(120,240)
            assert(joined, "manager must listen for human world entry")
            joined(TheWorld,player)
            flush()
            assert(#spawned==1, "configured companion did not spawn after human entry")
            local x,y,z=spawned[1].Transform:GetWorldPosition()
            assert(math.abs(x-120)<8 and math.abs(z-240)<8, "companion must spawn beside human, not origin")
            assert(spawned[1]:HasTag("ai_player"))
            joined(TheWorld,player)
            flush()
            assert(#spawned==1, "repeat player events must not duplicate companions")
        ''')

    def test_caves_do_not_duplicate_companions(self):
        lua = self.runtime(primary=False)
        lua.execute('human(120,240); if joined then joined(TheWorld,AllPlayers[1]) end; flush(); assert(#spawned==0, "secondary shard spawned duplicate companions")')


if __name__ == '__main__':
    unittest.main()
