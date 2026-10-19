"""Run the real plan module in Lua 5.1 with native-shaped, mutable evidence."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            ACTIONS={CHOP={}, MINE={}}
            Ents={}
            function entity(prefab, guid)
                local e={prefab=prefab,GUID=guid,components={},x=0,z=0}
                function e:IsValid() return not self.removed end
                function e:HasTag(tag) return self.ghost and tag=='playerghost' end
                e.Transform={GetWorldPosition=function() return e.x,0,e.z end}
                Ents[guid]=e
                return e
            end
            bot=entity('wilson',1)
            bot.components.health={IsDead=function() return bot.dead or false end}
            bot.sg={HasStateTag=function(_,tag) assert(tag=='busy'); return bot.busy end}
            function bot:GetBufferedAction() return bot.buffered end
            owned,equipped,dispatches={},{},{}
            bot.components.inventory={
                FindItems=function(_,predicate)
                    local result={}
                    for _,item in ipairs(owned) do if predicate(item) then result[#result+1]=item end end
                    return result
                end,
                GetEquippedItem=function(_,slot) return equipped[slot] end,
            }
            bot.components.locomotor={}
            observation={inventory={},equipment={},nearby={},structures={},recipes={},hunger={current=20}}
            function observe(inst) assert(inst==bot); return observation end
            function apply(inst, action)
                assert(inst==bot)
                dispatches[#dispatches+1]=action
                if on_apply then return on_apply(inst,action) end
                return true
            end
            function tick(t) return Plan.Tick(bot,plan,t,apply,observe) end
            function start(steps)
                plan=assert(Plan.New({plan=steps},0))
            end
            function resource(name,guid,action,left,product)
                local e=entity(name,guid)
                e.left=left
                if left then e.components.workable={GetWorkLeft=function() return e.left end} end
                local d={prefab=name,guid=guid,actions={action},work_left=left,product=product}
                observation.nearby[#observation.nearby+1]=d
                return e,d
            end
            function tool(name,guid,action)
                local e=entity(name,guid)
                e.components.equippable={equipslot='hands',IsRestricted=function() return false end}
                e.components.tool={CanDoAction=function(_,work) return work==action end}
                e.components.finiteuses={GetUses=function() return e.broken and 0 or 20 end}
                owned[#owned+1]=e
                observation.inventory[name]=1
                return e
            end
        ''')
        self.lua.globals().Plan = self.lua.execute(
            (ROOT / 'scripts/ai_plan.lua').read_text(encoding='utf-8'))

    def run_lua(self, source):
        self.lua.execute(source)

    def test_validation_is_atomic_and_copies_primitives(self):
        self.run_lua('''
            local bad={
                {plan={}}, {plan={{action='gather'}, {action='attack'}}},
                {plan={{action='wait',message='unknown'}}},
                {plan={{action='gather',target={}}}},
                {plan={{action='gather',target=0/0}}},
                {plan={{action='gather',target=math.huge}}},
                {plan={{action='gather',target=string.rep('x',129)}}},
                {plan={[1]={action='wait'},[3]={action='wait'}}},
                {plan={{action='gather'},{action='gather'},{action='gather'},
                    {action='gather'},{action='gather'},{action='gather'}}},
                {plan={{action='wait'},{action='gather'}}},
                {plan={{action='explore',x='1',z=2}}},
            }
            for _,result in ipairs(bad) do
                local p,reason=Plan.New(result,0)
                assert(p==nil and type(reason)=='string')
            end
            local result={action='gather',target='grass',message='manager speech',goal='food'}
            local p=assert(Plan.New(result,0))
            result.target='flint'
            assert(p.steps[1].target=='grass' and p.steps[1].message==nil)
        ''')

    def test_dispatch_and_idle_cannot_advance_and_success_is_delayed(self):
        self.run_lua('''
            resource('grass',10,'pick',nil,'cutgrass')
            start({{action='gather',target='grass'},{action='wait'}})
            assert(tick(0)=='running' and plan.index==1 and #dispatches==1)
            assert(dispatches[1].target_guid==10)
            assert(tick(.25)=='running' and plan.index==1 and #dispatches==1)
            assert(tick(.5)=='running' and plan.index==1 and #dispatches==1)
            observation.inventory.flint=5
            assert(tick(.75)=='running' and plan.index==1)
            observation.inventory.cutgrass=1
            assert(tick(1)=='running' and plan.index==2 and #dispatches==1)
            assert(tick(1.25)=='running' and #dispatches==2)
        ''')

    def test_snapshot_precedes_synchronous_dispatch_and_quarter_tick(self):
        self.run_lua('''
            observation.recipes.axe={accessible=true,ingredients_available=true}
            on_apply=function()
                assert(plan.snapshot.counts.axe==nil)
                observation.inventory.axe=1
                return true
            end
            start({{action='craft',recipe='axe'}})
            assert(tick(0)=='running')
            assert(tick(.249)=='running' and plan.index==1)
            assert(tick(.25)=='completed' and #dispatches==1)
        ''')

    def test_bound_target_does_not_fall_back_to_different_resource(self):
        self.run_lua('''
            local target=resource('grass',10,'pick',nil,'cutgrass')
            resource('grass',11,'pick',nil,'cutgrass')
            start({{action='gather',target='grass'},{action='wait'}})
            tick(0)
            target.removed=true
            table.remove(observation.nearby,1)
            assert(tick(.25)=='failed' and plan.reason=='target unavailable')
            assert(#dispatches==1 and dispatches[1].target_guid==10)
        ''')

    def test_invalid_target_and_materials_stop_before_apply(self):
        self.run_lua('''
            start({{action='gather',target_guid=999},{action='wait'}})
            assert(tick(0)=='failed' and #dispatches==0)
            observation.recipes.axe={accessible=true,ingredients_available=false}
            start({{action='craft',recipe='axe'},{action='wait'}})
            assert(tick(0)=='failed' and #dispatches==0)
            observation.recipes.axe.ingredients_available=true
            on_apply=function() return false end
            start({{action='craft',recipe='axe'},{action='wait'}})
            assert(tick(0)=='failed' and #dispatches==1)
            assert(tick(1)=='failed' and #dispatches==1)
        ''')

    def test_each_native_busy_source_waits_without_manager_queue(self):
        self.run_lua('''
            resource('grass',10,'pick',nil,'cutgrass')
            for _,mode in ipairs({'sg','buffered','locomotor'}) do
                start({{action='gather',target='grass'}})
                bot.busy=mode=='sg'
                bot.buffered=mode=='buffered' and {} or nil
                bot.components.locomotor.bufferedaction=mode=='locomotor' and {} or nil
                assert(tick(0)=='running' and #dispatches==0)
                assert(plan.snapshot==nil and bot._ai_pending_action==nil)
                bot.busy=false; bot.buffered=nil; bot.components.locomotor.bufferedaction=nil
            end
            assert(tick(.25)=='running' and #dispatches==1)
        ''')

    def test_revalidates_next_step_after_previous_effects(self):
        self.run_lua('''
            resource('grass',10,'pick',nil,'cutgrass')
            observation.recipes.axe={accessible=true,ingredients_available=true}
            start({{action='gather',target='grass'},{action='craft',recipe='axe'}})
            tick(0)
            observation.inventory.cutgrass=1
            assert(tick(.25)=='running' and #dispatches==1)
            observation.recipes.axe.ingredients_available=false
            assert(tick(.5)=='failed' and #dispatches==1)
        ''')

    def test_build_requires_new_matching_guid(self):
        self.run_lua('''
            observation.recipes.researchlab={accessible=true,ingredients_available=true}
            observation.structures={{guid=20,prefab='researchlab'}}
            start({{action='build',recipe='researchlab'}})
            tick(0)
            assert(tick(.25)=='running')
            observation.structures[2]={guid=21,prefab='campfire'}
            assert(tick(.5)=='running')
            observation.structures[3]={guid=22,prefab='researchlab'}
            assert(tick(.75)=='completed')
        ''')

    def test_eat_needs_food_loss_and_hunger_gain(self):
        self.run_lua('''
            local berries=entity('berries',30); owned={berries}
            observation.inventory.berries=2
            start({{action='eat',item='berries'}})
            tick(0)
            observation.inventory.berries=1
            assert(tick(.25)=='running')
            observation.hunger.current=25
            assert(tick(.5)=='completed')
        ''')

    def test_equip_requires_real_item_in_equipment_slot(self):
        self.run_lua('''
            local axe=tool('axe',30,ACTIONS.CHOP)
            start({{action='equip',item='axe'}})
            tick(0)
            observation.equipment.hands='axe'
            assert(tick(.25)=='running')
            equipped.hands=axe
            assert(tick(.5)=='completed')
        ''')

    def test_chop_and_mine_need_actual_work_progress(self):
        self.run_lua('''
            for _,kind in ipairs({'chop','mine'}) do
                observation.nearby={}; owned={}; observation.inventory={}
                local action=kind=='chop' and ACTIONS.CHOP or ACTIONS.MINE
                local axe=tool('tool',30,action)
                local target,d=resource('resource',10,kind,3)
                start({{action=kind,target_guid=10}})
                tick(0)
                assert(dispatches[#dispatches].item==30)
                assert(tick(.25)=='running')
                target.left=2; d.work_left=2
                assert(tick(.5)=='running')
                observation.nearby={}; target.removed=true
                bot._ai_survival_work={target=target,tool=axe}
                assert(tick(.75)=='completed')
                assert(bot._ai_survival_work==nil)
            end
        ''')

    def test_work_vanishing_without_progress_fails_and_zero_work_completes(self):
        self.run_lua('''
            tool('axe',30,ACTIONS.CHOP)
            local target,d=resource('tree',10,'chop',3)
            start({{action='chop',target='tree'}})
            tick(0)
            target.removed=true; observation.nearby={}
            assert(tick(.25)=='failed')
            target,d=resource('tree',11,'chop',3)
            start({{action='chop',target='tree'}})
            tick(0)
            target.left=0; observation.nearby={}
            assert(tick(.25)=='completed')
        ''')

    def test_tool_breaks_or_disappears_stops_work(self):
        self.run_lua('''
            local axe=tool('axe',30,ACTIONS.CHOP)
            resource('tree',10,'chop',3)
            start({{action='chop',target='tree'}})
            tick(0); axe.broken=true
            bot._ai_survival_work={}
            assert(tick(.25)=='failed' and plan.reason=='tool unavailable')
            assert(bot._ai_survival_work==nil)
            axe.broken=false
            start({{action='chop',target='tree'}})
            tick(0); owned={}
            assert(tick(.25)=='failed' and plan.reason=='tool unavailable')
        ''')

    def test_explore_uses_manager_destination_and_actual_position(self):
        self.run_lua('''
            on_apply=function()
                bot._ai_exploration={destination={x=18,z=0}}
                return true
            end
            start({{action='explore'}})
            tick(0)
            assert(tick(.25)=='running')
            bot.x=14.9
            assert(tick(.5)=='running')
            bot.x=15
            assert(tick(.75)=='completed')
        ''')

    def test_move_requires_station_range_three(self):
        self.run_lua('''
            local station=entity('researchlab',90)
            observation.structures={{guid=90,prefab='researchlab',x=12,z=0}}
            start({{action='move',target='researchlab'}})
            tick(0)
            assert(dispatches[1].target_guid==90)
            assert(tick(.25)=='running')
            bot.x=9
            assert(tick(.5)=='completed')
        ''')

    def test_wait_follow_and_say_hold_without_redispatch(self):
        self.run_lua('''
            for _,kind in ipairs({'wait','follow'}) do
                start({{action=kind}}); plan.hold_seconds=8
                local count=#dispatches
                tick(0)
                assert(tick(5)=='running' and #dispatches==count+1)
                assert(tick(8)=='completed' and #dispatches==count+1)
            end
            start({{action='wait'}}); plan.hold_seconds=90
            tick(0)
            assert(tick(44)=='running')
            assert(tick(45)=='failed' and plan.reason=='step timeout')
            plan=assert(Plan.New({action='say',message='manager owns speech'},0))
            local count=#dispatches
            assert(tick(0)=='running')
            assert(tick(.25)=='completed' and #dispatches==count)
        ''')

    def test_step_and_plan_timeout_clear_model_work(self):
        self.run_lua('''
            resource('grass',10,'pick',nil,'cutgrass')
            start({{action='gather',target='grass'}})
            tick(0); bot._ai_survival_work={}; bot._ai_pending_action={}
            assert(tick(45)=='failed' and plan.reason=='step timeout')
            assert(bot._ai_survival_work==nil and bot._ai_pending_action==nil)
            start({{action='gather',target='grass'}})
            assert(tick(180)=='failed' and plan.reason=='plan timeout')
            tool('axe',30,ACTIONS.CHOP)
            resource('tree',11,'chop',10)
            start({{action='chop',target='tree'}})
            tick(0)
            assert(tick(45)=='running')
            assert(tick(60)=='failed' and plan.reason=='step timeout')
        ''')

    def test_death_ghost_and_safety_cancel(self):
        self.run_lua('''
            for _,kind in ipairs({'dead','ghost','removed'}) do
                start({{action='wait'}}); bot[kind]=true
                assert(tick(0)=='failed' and #dispatches==0)
                bot[kind]=false
            end
            start({{action='wait'}}); tick(0)
            bot._ai_survival_work={}; bot._ai_pending_action={}
            assert(Plan.Cancel(bot,plan,'safety')=='failed')
            assert(plan.reason=='safety' and bot._ai_survival_work==nil and bot._ai_pending_action==nil)
            assert(tick(1)=='failed' and #dispatches==1)
            Plan.Cancel(bot,plan,'RAW SECRET OUTPUT')
            assert(plan.reason=='cancelled')
        ''')

    def test_callback_errors_have_fixed_reasons(self):
        self.run_lua('''
            start({{action='wait'}})
            on_apply=function() error('RAW SECRET OUTPUT') end
            assert(tick(0)=='failed' and plan.reason=='action rejected')
            start({{action='wait'}})
            observe=function() error('RAW SECRET OUTPUT') end
            assert(tick(0)=='failed' and plan.reason=='observation unavailable')
        ''')


if __name__ == '__main__':
    unittest.main()
