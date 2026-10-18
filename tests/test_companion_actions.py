"""Exercise companion actions against strict native-shaped Lua 5.1 APIs."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class CompanionActionsTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        self.lua.execute('''
            requests, tasks, found, moves, pushed, spoken = {}, {}, {}, {}, {}, {}
            decode_count = 0
            package.preload.ai_provider = function() return {} end
            package.preload.json = function()
                return {decode=function(content)
                    decode_count = decode_count + 1
                    assert(content == "fixture-say", "unexpected response fixture")
                    return {action="say", message="late response"}
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
            assert(companion._ai_mode=="wander")
        ''')

    def test_gather_pushes_pick_buffered_action(self):
        self.lua.execute('''
            local plant=entity(14,2,37)
            plant.prefab="berrybush"
            plant.components.pickable={CanBePicked=function() return true end}
            found={companion, plant}
            manager:ApplyAction(companion, {action="gather", target="berrybush"})
            assert(find_calls==1, "gather did not query nearby native entities")
            assert(#pushed==1 and pushed[1].target==plant)
            assert(pushed[1].action==ACTIONS.PICK and companion._ai_mode=="gather")
            assert(#spoken==0, "gather must act, not just announce an intention")
        ''')

    def test_gather_pushes_pickup_buffered_action(self):
        self.lua.execute('''
            local item=entity(14,2,37)
            item.prefab="twigs"
            item.components.inventoryitem={canbepickedup=true}
            found={item}
            manager:ApplyAction(companion, {action="gather", target="twigs"})
            assert(find_calls==1 and #pushed==1)
            assert(pushed[1].target==item and pushed[1].action==ACTIONS.PICKUP)
        ''')

    def test_gather_does_not_dispatch_unavailable_resource(self):
        self.lua.execute('''
            local plant=entity(14,2,37)
            plant.prefab="berrybush"
            plant.components.pickable={CanBePicked=function() return false end}
            found={plant}
            manager:ApplyAction(companion, {action="gather", target="berrybush"})
            assert(find_calls==1 and #pushed==0)
        ''')

    def test_timeout_releases_busy_and_late_callback_cannot_affect_next_request(self):
        self.lua.execute('''
            companion._ai_mode="wander"
            manager:Think(companion)
            assert(find_calls==1 and companion._ai_busy and #requests==1)
            assert(#tasks==1 and tasks[1].delay==60)
            manager:Think(companion)
            assert(#requests==1, "busy companion issued overlapping requests")
            tasks[1]:run()
            assert(not companion._ai_busy, "timeout left companion permanently busy")
            assert(companion._ai_mode=="follow", "timeout did not restore local following")
            manager:Think(companion)
            assert(companion._ai_busy and #requests==2)
            requests[1]("fixture-say", nil)
            assert(companion._ai_busy, "old response released newer request's busy lock")
            assert(decode_count==0 and #spoken==0, "late response was applied")
            assert(not tasks[2].cancelled, "old response cancelled the newer request timeout")
            requests[2]("fixture-say", nil)
            assert(not companion._ai_busy and tasks[2].cancelled)
            assert(decode_count==1 and #spoken==1 and spoken[1]=="late response")
            requests[2]("fixture-say", nil)
            assert(decode_count==1 and #spoken==1, "duplicate callback applied twice")
        ''')


if __name__ == '__main__':
    unittest.main()
