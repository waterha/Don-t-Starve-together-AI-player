"""Run the actual progression Lua module against deterministic observations."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class ProgressionTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().Progression = self.lua.execute(
            (ROOT / "scripts/ai_progression.lua").read_text(encoding="utf-8"))
        self.lua.execute('''
            bot, actions = {}, {}
            function observation(inventory)
                return {inventory=inventory or {}, equipment={}, nearby={}, structures={},
                    recipes={}, craftable={}, light={phase='day'}, hunger={percent=.9}}
            end
            function target(prefab, guid, action, distance)
                return {prefab=prefab, guid=guid, actions={action}, distance=distance or 1}
            end
            function recipe(o, name, ingredients, accessible, available)
                o.recipes[name]={known=accessible, accessible=accessible,
                    ingredients_available=available, ingredients=ingredients}
            end
            function dispatch(action)
                actions[#actions+1]=action
                return dispatch_result ~= false
            end
            function tick(o)
                local result=Progression.Tick(bot,o,dispatch)
                return actions[#actions], result
            end
            function supplied(extra)
                local inv={cutgrass=4,twigs=4}
                for name,amount in pairs(extra or {}) do inv[name]=amount end
                return observation(inv)
            end
        ''')

    def run_lua(self, source):
        self.lua.execute(source)

    def test_supplies_target_only_real_deficits_and_pickable_products(self):
        self.run_lua('''
            local o=observation({cutgrass=4,twigs=2})
            o.nearby={target('cutgrass',1,'pickup'),target('carrot',2,'pickup'),
                target('sapling',3,'pick'),target('twigs',4,'pickup',5)}
            local a=tick(o)
            assert(a.action=='gather' and a.target_guid==3)
            local s=Progression.Observe(bot,o)
            assert(s.goal=='supplies' and s.missing.twigs==2 and not s.missing.cutgrass)
            o.inventory.twigs=4
            a=tick(o)
            assert(a.action=='explore', 'must not arbitrarily pick grass, twigs or food at cap')
            assert(Progression.Observe(bot,o).goal=='axe')
        ''')

    def test_tool_dependencies_before_work_and_only_observed_outputs_advance(self):
        self.run_lua('''
            local o=supplied()
            o.nearby={target('evergreen',9,'chop'),target('flint',10,'pickup')}
            local a=tick(o)
            assert(a.action=='gather' and a.target_guid==10)
            o.inventory.flint=1
            o.craftable={'axe'}
            a=tick(o)
            assert(a.action=='craft' and a.recipe=='axe')
            assert(Progression.Observe(bot,o).goal=='axe', 'dispatch did not create an axe')
            o.inventory.axe=1
            a=tick(o)
            assert(a.action=='chop' and a.item=='axe' and a.target_guid==9)
            assert(Progression.Observe(bot,o).missing.log==6)
            o.inventory.log=6
            o.nearby={target('rock2',11,'mine'),target('flint',12,'pickup')}
            a=tick(o)
            assert(a.action=='gather' and a.target_guid==12, 'pickaxe needs two flint')
            assert(Progression.Observe(bot,o).goal=='pickaxe')
            o.inventory.flint=2; o.craftable={'pickaxe'}
            a=tick(o)
            assert(a.action=='craft' and a.recipe=='pickaxe')
            o.inventory.pickaxe=1
            a=tick(o)
            assert(a.action=='mine' and a.item=='pickaxe' and a.target_guid==11)
        ''')

    def test_equipped_hands_tools_skip_recraft_and_collect_drops_before_work(self):
        self.run_lua('''
            local o=supplied()
            o.equipment.hands='axe'
            o.nearby={target('evergreen',1,'chop'),target('log',2,'pickup')}
            local a=tick(o)
            assert(a.action=='gather' and a.target_guid==2)
            o.nearby={target('evergreen',1,'chop')}
            a=tick(o)
            assert(a.action=='chop' and a.item=='axe')
            o.inventory.log=6; o.equipment.hands='pickaxe'
            o.nearby={target('rock2',3,'mine')}
            a=tick(o)
            assert(a.action=='mine' and a.item=='pickaxe')
        ''')

    def test_gold_dependency_does_not_loop_on_plain_boulders(self):
        self.run_lua('''
            local o=supplied({log=6,pickaxe=1,rocks=4})
            o.nearby={target('rock1',1,'mine'),target('rock2',2,'mine')}
            local a=tick(o)
            assert(a.action=='mine' and a.target_guid==2)
            o.nearby={target('rock1',1,'mine')}
            a=tick(o)
            assert(a.action=='explore', 'plain boulders cannot satisfy missing gold')
            o.nearby={target('rocks',3,'pickup'),target('goldnugget',4,'pickup')}
            a=tick(o)
            assert(a.action=='gather' and a.target_guid==4)
        ''')

    def test_recipe_access_and_actual_observed_ingredients_are_required(self):
        self.run_lua('''
            local o=supplied({log=6,rocks=4,goldnugget=1,axe=1})
            recipe(o,'researchlab',{{prefab='log',amount=8},{prefab='rocks',amount=4},
                {prefab='goldnugget',amount=1}},true,false)
            o.nearby={target('log',1,'pickup')}
            local a=tick(o)
            assert(a.action=='gather' and a.target_guid==1)
            assert(Progression.Observe(bot,o).missing.log==2)
            o.inventory.log=8
            a=tick(o)
            assert(a.action=='explore', 'native ingredient availability is authoritative')
            o.recipes.researchlab.ingredients_available=true
            o.recipes.researchlab.accessible=false; o.recipes.researchlab.known=false
            a=tick(o)
            assert(a.action=='explore', 'cannot invent a recipe unlock')
            o.recipes.researchlab.accessible=true
            a=tick(o)
            assert(a.action=='build' and a.recipe=='researchlab')
            assert(Progression.Observe(bot,o).goal=='researchlab')
        ''')

    def test_observed_science_is_persistent_and_dispatch_never_completes(self):
        self.run_lua('''
            local o=supplied({log=6,rocks=4,goldnugget=1,flint=2})
            o.craftable={'researchlab'}
            assert(tick(o).action=='build')
            Progression.Record(bot,{action='build',recipe='researchlab'},true)
            assert(Progression.Observe(bot,o).goal=='researchlab')
            o.structures={{guid=77,prefab='researchlab',distance=3}}
            assert(Progression.Observe(bot,o).goal=='backpack')
            o.equipment.body='backpack'
            assert(Progression.Observe(bot,o).goal=='maintain')
            o.structures={}; o.inventory.log=2
            assert(Progression.Observe(bot,o).goal=='axe', 'remember science and replace missing camp tools')
            local other={_ai_camp={prefab='researchlab',guid=88}}
            assert(Progression.Observe(other,o).goal=='axe', 'accept native build event camp record')
        ''')

    def test_rejected_and_stuck_targets_are_incomplete_and_eventually_explore(self):
        self.run_lua('''
            local o=supplied(); o.nearby={target('flint',5,'pickup')}
            dispatch_result=false
            local a,result=tick(o)
            assert(not result and a.target_guid==5)
            local s=Progression.Observe(bot,o)
            assert(s.blocked and s.goal=='axe' and s.missing.flint==1)
            assert(s.last_action.dispatched==false)
            tick(o); tick(o)
            dispatch_result=true
            a=tick(o)
            assert(a.action=='explore', 'must leave a repeatedly stuck target')
            assert(Progression.Observe(bot,o).missing.flint==1)
            bot={}; actions={}
            for i=1,3 do assert(tick(o).action=='gather') end
            assert(tick(o).action=='explore', 'accepted dispatch without observed progress is not success')
        ''')

    def test_per_bot_state_and_snapshot_do_not_alias(self):
        self.run_lua('''
            local a,b={},{}
            local one=Progression.Observe(a,observation())
            local two=Progression.Observe(b,supplied({axe=1}))
            assert(one.goal=='supplies' and two.goal=='logs')
            one.missing.cutgrass=99
            assert(a._ai_progression.missing.cutgrass==4)
            Progression.Record(a,{action='gather',target_guid=9},false)
            assert(not b._ai_progression.last_action and not b._ai_progression.blocked)
            local snapshot=Progression.Observe(a,observation())
            snapshot.last_action.action='build'
            assert(a._ai_progression.last_action.action=='gather')
        ''')

    def test_maintenance_is_bounded_and_explores_instead_of_unlimited_pickups(self):
        self.run_lua('''
            local o=supplied({log=6,rocks=4,goldnugget=1,flint=2,axe=1,pickaxe=1})
            o.structures={{prefab='researchlab'}}
            o.equipment.body='backpack'
            o.nearby={target('cutgrass',1,'pickup'),target('twigs',2,'pickup'),
                target('log',3,'pickup'),target('flint',4,'pickup'),target('rocks',5,'pickup'),
                target('goldnugget',6,'pickup'),target('evergreen',7,'chop'),target('rock2',8,'mine')}
            for i=1,20 do
                local a=tick(o)
                assert(a.action=='explore')
                assert(next(Progression.Observe(bot,o).missing)==nil)
            end
            o.inventory.log=5
            local a=tick(o)
            assert(a.action=='gather' and a.target_guid==3)
            local state=Progression.Observe(bot,o)
            assert(state.missing.log==1 and not state.missing.rocks)
            o.inventory.log=999
            assert(tick(o).action=='explore')
        ''')

    def test_backpack_requires_station_approach_recipe_and_observed_output(self):
        self.run_lua('''
            local o=supplied({log=6,rocks=4,goldnugget=1})
            o.structures={{guid=7,prefab='researchlab',distance=8}}
            recipe(o,'backpack',{{prefab='cutgrass',amount=4},{prefab='twigs',amount=4}},false,true)
            local a=tick(o)
            assert(a.action=='move' and a.target_guid==7)
            o.structures[1].distance=2
            o.recipes.backpack.accessible=true
            a=tick(o)
            assert(a.action=='craft' and a.recipe=='backpack')
            assert(Progression.Observe(bot,o).goal=='backpack', 'dispatch did not create the backpack')
            o.inventory.backpack=1
            a=tick(o)
            assert(a.action=='equip' and a.item=='backpack')
            assert(Progression.Observe(bot,o).goal=='equip_backpack')
            o.equipment.body='backpack'
            assert(Progression.Observe(bot,o).goal=='pickaxe', 'camp mineral reserve needs a pickaxe')
        ''')

    def test_native_usable_tools_override_broken_inventory_and_equipment(self):
        self.run_lua('''
            local o=supplied({axe=1,flint=1})
            o.equipment.hands='axe'; o.tools={}
            o.craftable={'axe'}
            o.nearby={target('evergreen',1,'chop')}
            local a=tick(o)
            assert(a.action=='craft' and a.recipe=='axe', 'broken axe is not usable')
            o.tools.axe=true
            a=tick(o)
            assert(a.action=='chop')
            o.inventory.log=6; o.inventory.pickaxe=1; o.tools.pickaxe=false
            o.nearby={target('rock2',2,'mine')}
            a=tick(o)
            assert(a.action=='explore', 'must not mine using exhausted pickaxe')
        ''')

    def test_maintenance_rebuilds_missing_tools_without_rebuilding_science(self):
        self.run_lua('''
            local o=supplied({log=5,rocks=4,goldnugget=1,flint=2})
            o.structures={{prefab='researchlab'}}; o.equipment.body='backpack'
            o.craftable={'axe','pickaxe'}
            assert(tick(o).recipe=='axe')
            o.inventory.axe=1
            o.nearby={target('evergreen',1,'chop')}
            assert(tick(o).action=='chop')
            o.inventory.log=6; o.inventory.rocks=3
            assert(tick(o).recipe=='pickaxe')
            o.inventory.pickaxe=1; o.nearby={target('rock1',2,'mine')}
            assert(tick(o).action=='mine')
            assert(bot._ai_progression.built.researchlab)
        ''')

    def test_buffered_science_placement_does_not_regather_consumed_ingredients(self):
        self.run_lua('''
            local o=supplied()
            recipe(o,'researchlab',{{prefab='log',amount=4},{prefab='rocks',amount=4},
                {prefab='goldnugget',amount=1}},true,false)
            o.recipes.researchlab.buffered=true
            local a=tick(o)
            assert(a.action=='build' and a.recipe=='researchlab')
            assert(not bot._ai_progression.built.researchlab)
        ''')

    def test_action_records_drop_entity_references_and_station_distance_is_progress(self):
        self.run_lua('''
            Progression.Record(bot,{action='gather',target={components={}},target_guid=1},false)
            assert(bot._ai_progression.last_action.target==nil)
            local o=supplied()
            o.structures={{guid=8,prefab='researchlab',distance=10}}
            recipe(o,'backpack',{{prefab='cutgrass',amount=4},{prefab='twigs',amount=4}},false,true)
            for distance=10,4,-1 do
                o.structures[1].distance=distance
                assert(tick(o).action=='move', 'approach progress must not be mistaken for a stuck target')
                assert(not Progression.Observe(bot,o).blocked)
            end
        ''')

    def test_busy_observation_does_not_dispatch_or_increment_retry(self):
        self.run_lua('''
            local o=supplied(); o.busy=true; o.nearby={target('flint',1,'pickup')}
            assert(not Progression.Tick(bot,o,dispatch))
            assert(#actions==0 and bot._ai_progression.attempts==0)
            o.busy=false
            assert(tick(o).action=='gather')
        ''')

    def test_shortages_stay_positive_and_bounded_across_repeated_observations(self):
        self.run_lua('''
            local o=observation()
            for i=1,100 do
                local s=Progression.Observe(bot,o)
                assert(s.missing.cutgrass==4 and s.missing.twigs==4)
            end
            o=supplied({log=6})
            for i=1,100 do
                local s=Progression.Observe(bot,o)
                assert(s.goal=='pickaxe' and s.missing.flint==2)
            end
            o.inventory.flint=3
            assert(next(Progression.Observe(bot,o).missing)==nil)
        ''')


if __name__ == "__main__":
    unittest.main()
