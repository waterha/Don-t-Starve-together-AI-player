"""Manager wiring for short plans: dispatch, evidence, completion and re-decision."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class PlanIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        lua = self.lua
        lua.globals().package.path = str(ROOT / 'scripts' / '?.lua').replace('\\', '/') + ';' + lua.globals().package.path
        lua.execute('''
            clock, requests, spoken, survival_calls = 0, {}, {}, {}
            function GetTime() return clock end
            package.preload.json = function() return {
                encode = function() return "observation" end,
                decode = function() return response end,
            } end
            package.preload.ai_survival = function() return {
                Observe = function(inst) return {inventory = {}, nearby = {}, structures = {},
                    recipes = {}, hunger = {current = 100, max = 100, percent = 1}} end,
                Tick = function(inst) survival_calls[#survival_calls+1] = "tick"; return false end,
                Continue = function(inst) survival_calls[#survival_calls+1] = "continue" end,
                EmergencyTick = function(inst) return emergency end,
                Apply = function(inst, action) survival_calls[#survival_calls+1] = action.action; return true end,
            } end
            package.preload.ai_provider = function() return {} end
            package.preload.ai_players_roster = function() return {Publish = function() end} end
            package.preload.ai_dialogue = function() return {
                Begin = function() return 1 end, End = function() end, Observe = function() return {} end,
                Due = function() return false end, Tick = function() return nil end } end
            package.preload.ai_chat = function() return {
                Clean = function(s) return s end, Register = function() end,
                Say = function(inst, text) spoken[#spoken+1] = text end } end
            function Vector3(x, y, z) return {x = x, y = y, z = z} end
            TheWorld = {state = {phase = "day"}}
            function alive() return true end
            function is_ghost() return false end
            function available() return true end
            function find_human() return human end
            function say(inst, text) spoken[#spoken+1] = text end
            function auth_notice() end
            function is_human(e) return e == human end
            function GetModConfigData(name) return config[name] end
            config = {request_interval = 30}
            human = {userid = "owner", Transform = {GetWorldPosition = function() return 0, 0, 0 end},
                HasTag = function() return false end, IsValid = function() return true end}
            AllPlayers = {human}
            bot = {prefab = "wilson", GUID = 7, name = "Bot", tags = {},
                IsValid = function() return true end,
                HasTag = function(self, tag) return self.tags[tag] or false end,
                GetBufferedAction = function() return nil end,
                Transform = {GetWorldPosition = function() return 0, 0, 0 end},
                DoTaskInTime = function(self, delay, fn)
                    local task = {delay = delay, cancelled = false, fn = fn}
                    function task:Cancel() self.cancelled = true end
                    function task:run() if not self.cancelled then fn() end end
                    tasks[#tasks+1] = task
                    return task
                end,
                sg = {HasStateTag = function() return false end},
                components = {
                    health = {IsDead = function() return false end},
                    locomotor = {Stop = function() end},
                    inventory = {FindItems = function() return {} end},
                    playercontroller = {Enable = function() end},
                }}
            tasks = {}
            manager = require("ai_player_manager").new(function(name) return config[name] end)
            manager.players = {bot}
            bot._ai_index = 1
            bot._ai_provider = {Complete = function(self, messages, callback)
                requests[#requests+1] = callback
            end}
        ''')
        self.lua.execute('response = {goal = "rest", plan = {{action = "wait"}}, message = "ok"}')

    def test_plan_response_dispatches_locally_then_queues_a_new_decision(self):
        self.lua.execute('''
            manager:Think(bot)
            assert(#requests == 1 and bot._ai_busy)
            requests[1]("{}", nil)
            assert(not bot._ai_busy, "a plan must release the request lock")
            assert(bot._ai_plan and #bot._ai_plan.steps == 1, "plan was not retained")
            assert(bot._ai_feedback.status == "plan_received")
            -- The step is dispatched on the local tick, not by another model request.
            manager:UpdateLocal(bot)
            assert(bot._ai_plan.snapshot ~= nil, "step was not dispatched")
            assert(#requests == 1, "dispatching a plan step must not call the model")
            clock = 6
            manager:UpdateLocal(bot)
            assert(bot._ai_plan == nil, "a held wait step must complete locally")
            assert(bot._ai_feedback.status == "completed" and bot._ai_feedback.reason == "plan completed")
            -- Completion queues a decision that still honors the hard interval.
            clock = 40
            manager:UpdateLocal(bot)
            assert(#requests == 2, "completed plan must trigger a new decision after the interval")
        ''')

    def test_emergency_cancels_the_running_plan(self):
        self.lua.execute('''
            manager:Think(bot)
            requests[1]("{}", nil)
            assert(bot._ai_plan)
            emergency = true
            manager:UpdateLocal(bot)
            assert(bot._ai_plan == nil, "urgent survival must cancel the remaining plan")
            emergency = false
        ''')

    def test_invalid_plan_falls_back_to_the_single_action_format(self):
        self.lua.execute('''
            response = {action = "say", message = "hello", plan = {{action = "fly"}}}
            manager:Think(bot)
            requests[1]("{}", nil)
            assert(bot._ai_plan == nil, "an unsupported step must not start a plan")
            assert(bot._ai_feedback.status == "dispatched", "legacy action should still run")
        ''')

    def test_chat_request_can_preempt_a_running_plan(self):
        self.lua.execute('''
            manager:Think(bot)
            requests[1]("{}", nil)
            assert(bot._ai_plan and #requests == 1)
            require("ai_dialogue").Due = function() return true end
            clock = 31
            manager:UpdateLocal(bot)
            assert(#requests == 2, "pending chat must be requested while a plan runs")
        ''')


if __name__ == '__main__':
    unittest.main()
