"""Exercise companion actions against strict native-shaped Lua 5.1 APIs."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class CompanionActionsTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.globals().package.path = str(ROOT / 'scripts' / '?.lua').replace('\\', '/') + ';' + self.lua.globals().package.path
        self.lua.execute('''
            requests, tasks, found, moves, pushed, spoken = {}, {}, {}, {}, {}, {}
            decode_count = 0
            clock = 0
            function GetTime() return clock end
            package.preload.ai_provider = function() return {} end
            package.preload.ai_players_roster = function() return {Publish=function() end} end
            package.preload.ai_survival = function() return {
                Observe=function() return {hunger={percent=.2}, inventory={twigs=3}} end,
                Tick=function() return false end,
                Apply=function(inst, action) survival_action=action; return true end,
            } end
            package.preload.json = function()
                return {encode=function(observation)
                    assert(observation.inventory.twigs==3 and observation.hunger.percent==.2)
                    assert(observation.position.x==13 and observation.phase=="day")
                    observed_context=true
                    return "encoded survival observation"
                end, decode=function(content)
                    decode_count = decode_count + 1
                    assert(content == "fixture-say", "unexpected response fixture")
                    return {action="say", message="late response", ask=true}
                end}
            end
            function Vector3(x, y, z)
                assert(type(x)=="number" and type(y)=="number" and type(z)=="number")
                return {x=x, y=y, z=z, vector=true}
            end
            ACTIONS = {PICK={}, PICKUP={}, ATTACK={}}
            function BufferedAction(doer, target, action)
                assert(doer==companion, "action has wrong doer")
                assert(target and target.components, "action has invalid target")
                assert(action==ACTIONS.PICK or action==ACTIONS.PICKUP or action==ACTIONS.ATTACK)
                return {doer=doer, target=target, action=action, buffered=true}
            end
            function entity(x, y, z, userid, tags)
                local inst = {components={}, userid=userid, tags=tags or {}, valid=true}
                function inst:IsValid() return self.valid end
                function inst:HasTag(tag) return self.tags[tag] or false end
                inst.Transform = {GetWorldPosition=function() return x,y,z end}
                function inst:DoTaskInTime(delay, callback)
                    assert(type(delay)=="number" and delay>0)
                    local task = {delay=delay, cancelled=false}
                    function task:Cancel() self.cancelled=true end
                    function task:run() if not self.cancelled then callback(inst) end end
                    tasks[#tasks+1] = task
                    return task
                end
                return inst
            end
            companion = entity(13, 2, 37, "", {ai_player=true})
            companion._ai_index = 1
            companion._ai_mode = "follow"
            human = entity(100, 0, 200, "fixture-human")
            AllPlayers = {companion, human}
            companion.components.talker = {Say=function(_, text) spoken[#spoken+1]=text end}
            companion.components.locomotor = {
                GoToEntity=function(_, target, action, run)
                    assert(target==human, "follow target must be a real human, not AllPlayers[1]")
                    assert(action==nil or (type(action)=="table" and action.buffered),
                        "GoToEntity second argument must be a BufferedAction, not distance")
                    assert(run==nil or type(run)=="boolean")
                    moves[#moves+1] = {target=target, action=action, run=run}
                end,
                GoToPoint=function(_, point, action, run)
                    assert(type(point)=="table" and point.vector,
                        "GoToPoint needs Vector3, not numeric x,y,z")
                    assert(action==nil or (type(action)=="table" and action.buffered))
                    assert(run==nil or type(run)=="boolean")
                    moves[#moves+1] = {point=point, action=action, run=run}
                end,
                PushAction=function(_, action, run)
                    assert(type(action)=="table" and action.buffered,
                        "PushAction needs a real BufferedAction")
                    assert(run==nil or type(run)=="boolean")
                    pushed[#pushed+1] = action
                end,
                Stop=function() stopped=true end,
            }
            companion._ai_provider = {Complete=function(_, messages, callback)
                assert(type(messages)=="table" and #messages==2)
                requests[#requests+1] = callback
            end}
            TheWorld = {state={phase="day"}}
            TheSim = {FindEntities=function(_, x, y, z, radius, musttags, canttags)
                assert(x==13 and y==2 and z==37 and radius==12,
                    "FindEntities must receive all three coordinates and radius separately")
                assert(musttags==nil or type(musttags)=="table")
                assert(canttags==nil or type(canttags)=="table")
                find_calls = (find_calls or 0) + 1
                return found
            end}
        ''')
        self.lua.globals().Manager = self.lua.execute(
            (ROOT / 'scripts/ai_player_manager.lua').read_text(encoding='utf-8'))
        self.lua.execute('manager=Manager.new(function() return nil end)')

    def test_follow_skips_first_ai_and_uses_native_entity_arguments(self):
        self.lua.execute('''
            companion._ai_owner = companion
            manager:ApplyAction(companion, {action="follow"})
            assert(#moves==1 and moves[1].target==human)
            assert(moves[1].action==nil, "follow distance leaked into bufferedaction argument")
            assert(companion._ai_owner==human)
        ''')

    def test_wander_passes_vector_position_to_native_locomotor(self):
        self.lua.execute('''
            manager:ApplyAction(companion, {action="wander"})
            assert(#moves==1)
            local point=moves[1].point
            assert(point and point.y==2)
            assert(math.abs(point.x-13)<=4 and math.abs(point.z-37)<=4)
            assert(companion._ai_mode=="autonomous")
        ''')

    def test_survival_commands_are_forwarded_to_survival_module(self):
        self.lua.execute('''
            for _,name in ipairs({"gather","eat","craft","equip","chop","mine"}) do
                manager:ApplyAction(companion, {action=name, target="twigs", recipe="torch"})
                assert(survival_action.action==name and survival_action.recipe=="torch")
                assert(companion._ai_mode=="autonomous")
            end
        ''')

    def test_attack_ignores_players_and_malformed_targets(self):
        self.lua.execute('''
            human.prefab, human.GUID = "wilson", 41
            human.tags.player, human.components.combat = true, {}
            monster = entity(15, 2, 37, nil)
            monster.prefab, monster.GUID, monster.components.combat = "spider", 42, {}
            found = {human, monster}
            manager:ApplyAction(companion, {action="attack", target="wilson"})
            manager:ApplyAction(companion, {action="attack", target={prefab="spider"}})
            assert(#pushed==0, "player or malformed target triggered an attack")
            manager:ApplyAction(companion, {action="attack", target="42"})
            assert(#pushed==1 and pushed[1].target==monster)
            assert(find_calls and find_calls>=2)
        ''')

    def test_busy_model_action_is_retained_until_actor_is_available(self):
        self.lua.execute('''
            companion.components.locomotor.bufferedaction={work=true}
            manager:ApplyAction(companion, {action="gather", target="twigs"})
            assert(companion._ai_pending_action, "busy actor discarded model decision")
            assert(not survival_action)
            companion.components.locomotor.bufferedaction=nil
            manager:UpdateLocal(companion)
            assert(survival_action and survival_action.target=="twigs")
            assert(not companion._ai_pending_action)
        ''')

    def test_wait_response_does_not_interrupt_in_progress_work(self):
        self.lua.execute('''
            companion.components.locomotor.bufferedaction={work=true}
            manager:ApplyAction(companion, {action="wait"})
            assert(not stopped, "delayed wait response interrupted ongoing work")
        ''')

    def test_explicit_mode_change_clears_old_continuous_work(self):
        self.lua.execute('''
            for _, name in ipairs({"follow", "wander", "wait"}) do
                companion._ai_survival_work={target="old-tree"}
                manager:ApplyAction(companion, {action=name})
                assert(not companion._ai_survival_work)
            end
        ''')

    def test_expired_pending_action_is_discarded(self):
        self.lua.execute('''
            companion.components.locomotor.bufferedaction={work=true}
            manager:ApplyAction(companion, {action="gather", target="twigs"})
            clock=11
            companion.components.locomotor.bufferedaction=nil
            manager:UpdateLocal(companion)
            assert(not survival_action and not companion._ai_pending_action)
        ''')

    def test_model_goal_feedback_and_wait_are_preserved_without_local_planner(self):
        self.lua.execute('''
            companion._ai_mode="autonomous"
            local survival=require("ai_survival")
            survival.Tick=function() error("legacy survival selected a goal") end
            require("ai_progression").Tick=function() error("local progression overrode the model") end
            require("json").decode=function() return {goal="Explore coast",action="wait"} end
            manager:Think(companion); requests[1]("fixture",nil)
            assert(companion._ai_goal=="Explore coast" and stopped)
            assert(companion._ai_feedback.status=="dispatched")
            stopped=false
            for i=1,20 do clock=clock+.25; manager:UpdateLocal(companion) end
            assert(not survival_action and #moves==0, "wait was replaced by local gathering/exploration")
            require("json").encode=function(obs)
                assert(obs.autonomy.goal=="Explore coast" and obs.autonomy.feedback.action=="wait")
                return "fixture"
            end
            manager:Think(companion)
        ''')

    def test_model_exploration_coordinates_are_validated(self):
        self.lua.execute('''
            TheWorld.Map={IsPassableAtPoint=function() return true end,IsGroundTargetBlocked=function() return false end}
            assert(manager:ApplyAction(companion,{action="explore",x=23,z=47}))
            assert(moves[1].point.x==23 and moves[1].point.z==47)
            assert(not manager:ApplyAction(companion,{action="explore",x=10000,z=47}))
            assert(not manager:ApplyAction(companion,{action="explore",x=0/0,z=47}))
            assert(#moves==1)
            TheWorld.Map.IsPassableAtPoint=function() return false end
            assert(not manager:ApplyAction(companion,{action="explore",x=23,z=47}))
        ''')

    def test_only_emergency_can_preempt_a_queued_model_action(self):
        self.lua.execute('''
            companion._ai_mode="autonomous"
            local survival=require("ai_survival")
            survival.EmergencyTick=function() return true end
            companion._ai_pending_action={action={action="gather",target="twigs"},expires=10}
            manager:UpdateLocal(companion)
            assert(not survival_action and companion._ai_pending_action)
            survival.EmergencyTick=function() return false end
            manager:UpdateLocal(companion)
            assert(survival_action.target=="twigs")
        ''')

    def test_timeout_releases_busy_and_late_callback_cannot_affect_next_request(self):
        self.lua.execute('''
            companion._ai_mode="wander"
            manager:Think(companion)
            assert(observed_context and companion._ai_busy and #requests==1)
            assert(#tasks==1 and tasks[1].delay==60)
            manager:Think(companion)
            assert(#requests==1, "busy companion issued overlapping requests")
            tasks[1]:run()
            assert(not companion._ai_busy, "timeout left companion permanently busy")
            assert(companion._ai_mode=="autonomous", "timeout did not restore autonomous survival")
            manager:Think(companion)
            assert(companion._ai_busy and #requests==2)
            requests[1]("fixture-say", nil)
            assert(companion._ai_busy, "old response released newer request's busy lock")
            assert(decode_count==0 and #spoken==0, "late response was applied")
            assert(not tasks[2].cancelled, "old response cancelled the newer request timeout")
            requests[2]("fixture-say", nil)
            assert(not companion._ai_busy and tasks[2].cancelled)
            assert(decode_count==1 and #spoken==0, "autonomous action replies must not be broadcast as periodic plans")
            requests[2]("fixture-say", nil)
            assert(decode_count==1 and #spoken==0, "duplicate callback applied twice")
            companion._ai_provider.Complete=function(_,messages,callback)
                callback('fixture-say',nil)
            end
            manager:Think(companion)
            assert(#spoken==0, "autonomous model question must not bypass help cooldown")
        ''')


if __name__ == '__main__':
    unittest.main()
