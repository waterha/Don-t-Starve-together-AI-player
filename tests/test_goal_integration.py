"""Connect the actual goal planner to manager scheduling and strict native-shaped actions."""
import unittest

from tests import test_companion_actions as actions_fixture
from tests import test_companion_spawn as spawn_fixture
from tests import test_progression as progression_fixture
from tests import test_survival as survival_fixture


class GoalIntegrationTest(unittest.TestCase):
    def test_local_loop_does_not_choose_goals_during_inflight_model(self):
        fixture = actions_fixture.CompanionActionsTest()
        fixture.setUp()
        fixture.lua.execute('''
            local survival=require('ai_survival')
            survival.Observe=function() return {inventory={cutgrass=4,twigs=4,flint=1},
                craftable={'axe'}, nearby={}, recipes={}} end
            companion._ai_mode, companion._ai_busy='autonomous',true
            companion._ai_goal='Explore the coast'
            for i=1,10 do clock=i; manager:UpdateLocal(companion) end
            assert(survival_action==nil, 'local route must not craft an axe while the model chooses exploration')
            assert(companion._ai_goal=='Explore the coast' and #requests==0)
            survival.EmergencyTick=function() survival_action={action='eat'}; return true end
            manager:UpdateLocal(companion)
            assert(survival_action.action=='eat', 'immediate survival must still run while HTTP is pending')
        ''')

    def test_exploration_holds_destination_then_tries_unvisited_direction(self):
        fixture = actions_fixture.CompanionActionsTest()
        fixture.setUp()
        fixture.lua.execute('''
            TheWorld.Map={IsPassableAtPoint=function() return true end,
                IsGroundTargetBlocked=function() return false end}
            assert(manager:Explore(companion) and #moves==1)
            local initial=moves[1].point
            clock=1
            assert(manager:Explore(companion) and #moves==1, 'must not jitter-restart movement')
            clock=13
            assert(manager:Explore(companion) and #moves==2)
            assert(initial.x~=moves[2].point.x or initial.z~=moves[2].point.z)
            TheWorld.Map.IsPassableAtPoint=function() return false end
            clock=26
            assert(not manager:Explore(companion) and #moves==2)
        ''')

    def test_native_build_completion_not_dispatch_records_camp(self):
        fixture = spawn_fixture.BotLifecycleTest()
        lua = fixture.runtime(existing_human=True)
        lua.execute('''
            advance(2)
            requests[1].callback('{"character":"wilson"}',nil)
            local bot=spawned[1]
            assert(bot._ai_camp==nil)
            local structure={prefab='researchlab',GUID=777,
                IsValid=function() return true end,
                Transform={GetWorldPosition=function() return 10,0,20 end}}
            bot.listeners.buildstructure(bot,{item=structure})
            assert(bot._ai_camp.prefab=='researchlab' and bot._ai_camp.guid==777)
            assert(bot._ai_camp.x==10 and bot._ai_camp.z==20)
        ''')

    def test_work_progress_does_not_trigger_false_stuck_recovery(self):
        fixture = progression_fixture.ProgressionTest()
        fixture.setUp()
        fixture.lua.execute('''
            local o=supplied({axe=1})
            local tree=target('evergreen',22,'chop')
            o.nearby={tree}
            for remaining=12,1,-1 do
                tree.work_left=remaining
                local action=tick(o)
                assert(action.action=='chop', 'successful chopping is progress even before logs drop')
            end
        ''')

    def test_destroyed_station_no_longer_counts_as_completed(self):
        fixture = progression_fixture.ProgressionTest()
        fixture.setUp()
        fixture.lua.execute('''
            local o=supplied({log=6,rocks=4,goldnugget=1,axe=1,pickaxe=1})
            o.structures={{prefab='researchlab',guid=44,distance=2}}
            Ents={[44]={prefab='researchlab',IsValid=function() return true end}}
            assert(Progression.Observe(bot,o).goal=='backpack')
            Ents[44]=nil; o.structures={}
            assert(Progression.Observe(bot,o).goal=='researchlab')
        ''')

    def test_disliked_plant_food_has_finite_passive_collection_cap(self):
        fixture = survival_fixture.SurvivalTest()
        fixture.setUp()
        fixture.lua.execute('''
            local grass=loose('cutgrass')
            grass.components.stackable={StackSize=function() return 4 end}
            local twig=loose('twigs')
            twig.components.stackable={StackSize=function() return 4 end}
            local berries=food('berries')
            berries.disliked=true
            berries.components.stackable={StackSize=function() return 6 end}
            owned={grass,twig,berries}
            found={plant('berrybush','berries')}
            assert(not Survival.Tick(bot,true), 'must not gather plants endlessly when actor rejects them')
            assert(#pushed==0)
        ''')

    def test_darkness_and_critical_hunger_block_development(self):
        fixture = survival_fixture.SurvivalTest()
        fixture.setUp()
        fixture.lua.execute('''
            assert(Survival.CanDevelop(bot))
            TheWorld.state.phase,TheWorld.state.isnight='night',true
            bot.LightWatcher={GetLightValue=function() return 0 end}
            assert(not Survival.CanDevelop(bot))
            TheWorld.state.phase,TheWorld.state.isnight='day',false
            bot.components.hunger.current=1
            assert(not Survival.CanDevelop(bot))
        ''')


if __name__ == '__main__':
    unittest.main()
