"""Configuration reaches the server through the mod's bound accessor (Lua 5.1)."""
from pathlib import Path
import unittest
from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class ManagerConfigTest(unittest.TestCase):
    def test_bound_configuration_and_delayed_world_initialization(self):
        lua = LuaRuntime()
        lua.execute('''
            config = {ai_count=2, ai_1_api_key="fixture-key", ai_2_api_key="fixture-key", request_interval=60}
            function GetModConfigData(name, modname)
                assert(modname, "modname must be supplied manually")
                return config[name]
            end
            package.preload.ai_provider = function() return {} end
            package.preload.json = function() return {} end
            GLOBAL = _G
            function AddSimPostInit(callback) on_sim_init = callback end
        ''')
        manager = lua.execute((ROOT / "scripts/ai_player_manager.lua").read_text(encoding="utf-8"))
        lua.globals().Manager = manager
        lua.execute('''
            function require(name)
                assert(name == "ai_player_manager")
                return Manager
            end
            server_mod_env = setmetatable({
                GLOBAL = GLOBAL,
                GetModConfigData = function(name) return GetModConfigData(name, "ai_players") end,
                AddSimPostInit = AddSimPostInit,
                require = require,
            }, {__index=_G})
            spawned = {}
            function Manager:SpawnOne(index, key) spawned[index] = key end
        ''')
        run_main = lua.eval("function(code) local fn=assert(loadstring(code)); setfenv(fn,server_mod_env); fn() end")
        # Mod loading precedes world initialization; TheWorld is deliberately nil.
        run_main((ROOT / "modmain.lua").read_text(encoding="utf-8"))
        lua.execute('''
            AllPlayers = {{userid="fixture-human", IsValid=function() return true end,
                HasTag=function() return false end, Transform={}}}
            TheWorld = {
                ismastersim = true, ismastershard = true,
                ListenForEvent = function() end,
                DoTaskInTime = function(self, delay, callback) callback() end,
                DoPeriodicTask = function(self, delay, callback) interval = delay end,
            }
            on_sim_init()
            assert(spawned[1] == config.ai_1_api_key and spawned[2] == config.ai_2_api_key)
            assert(interval == 60)
            spawned = {}
            TheWorld.ismastersim = false
            on_sim_init()
            assert(next(spawned) == nil, "client must not start the manager")
        ''')


if __name__ == "__main__":
    unittest.main()
