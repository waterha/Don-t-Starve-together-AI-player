"""Strict Lua 5.1 fixtures for basic survival, not a DST engine simulation."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class SurvivalTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute('''
            ACTIONS = {}
            for _, name in ipairs({'PICK','PICKUP','EAT','CHOP','MINE','WALKTO'}) do ACTIONS[name]={id=name} end
            EQUIPSLOTS={HANDS='hands'}
            pushed, found, owned, equipped, recipes, crafted = {}, {}, {}, {}, {}, {}
            function Vector3(x,y,z) return {x=x,y=y,z=z} end
            function entity(prefab,x,z)
                local e={prefab=prefab, GUID=100, components={}, tags={}, x=x or 1, z=z or 0}
                function e:IsValid() return not self.removed end
                function e:HasTag(tag) return self.tags[tag] or false end
                e.Transform={GetWorldPosition=function() return e.x,0,e.z end}
                function e:GetDistanceSqToInst(other) return (self.x-other.x)^2+(self.z-other.z)^2 end
                return e
            end
            bot=entity('wilson',0,0)
            function bot:GetBufferedAction() return self.bufferedaction end
            bot.sg={HasStateTag=function(_,tag) assert(tag=='busy'); return bot.busy or false end}
            bot.components.locomotor={PushAction=function(self, act, run)
                assert(run==true and act.doer==bot)
                pushed[#pushed+1]=act
                self.bufferedaction=act
            end}
            function BufferedAction(doer,target,action,invobject,pos)
                assert(doer==bot and action)
                if action==ACTIONS.EAT then
                    assert(target==nil and invobject.components.edible, 'food must be invobject')
                elseif action==ACTIONS.CHOP or action==ACTIONS.MINE then
                    assert(invobject.components.tool:CanDoAction(action), 'actual tool must be invobject')
                    assert(equipped.hands==invobject, 'tool must be equipped')
                elseif action==ACTIONS.WALKTO then assert(pos and pos.x and pos.z)
                else assert(target, 'gather needs target') end
                return {doer=doer,target=target,action=action,invobject=invobject,pos=pos}
            end
            bot.components.inventory={
                IsOpenedBy=function(_,actor) return actor==bot end,
                equipslots=equipped,
                FindItems=function(_,predicate)
                    local result={}
                    for _, item in ipairs(owned) do if predicate(item) then result[#result+1]=item end end
                    return result
                end,
                IsFull=function() return full or false end,
                CanAcceptCount=function(_,item,n) assert(n==1); return full and 0 or 1 end,
                GetEquippedItem=function(_,slot) return equipped[slot] end,
                Equip=function(_,item)
                    assert(item.components.equippable and not item.components.equippable:IsRestricted(bot))
                    equipped[item.components.equippable.equipslot]=item
                    return true
                end,
            }
            function stat(current,maximum)
                return {current=current,max=maximum,GetPercent=function(self) return self.current/self.max end}
            end
            bot.components.hunger=stat(100,150)
            bot.components.sanity=stat(150,200)
            bot.components.health={currenthealth=100,maxhealth=150,GetPercent=function() return 2/3 end,IsDead=function() return false end}
            bot.components.eater={CanEat=function(_,item) return not item.inedible end,
                PrefersToEat=function(_,item) return not item.disliked end}
            bot.components.builder={
                KnowsRecipe=function(_,recipe) assert(type(recipe)=='table'); return not recipe.unknown end,
                HasIngredients=function(_,recipe) assert(type(recipe)=='table'); return recipe.available or false end,
                MakeRecipe=function(_,recipe) assert(recipe.available and not recipe.unknown); crafted[#crafted+1]=recipe.name; return true end,
                MakeRecipeFromMenu=function(self,recipe)
                    if self:MakeRecipe(recipe) then bot.components.locomotor.bufferedaction={action='BUILD'} end
                end,
            }
            function GetValidRecipe(name) return recipes[name] end
            function food(name,hunger,health,sanity)
                local item=entity(name)
                item.components.edible={GetHunger=function() return hunger or 10 end,
                    GetHealth=function() return health or 0 end,GetSanity=function() return sanity or 0 end}
                return item
            end
            function equipment(name,work)
                local item=entity(name)
                item.components.equippable={equipslot='hands',IsRestricted=function() return item.restricted or false end}
                item.components.fueled={IsEmpty=function() return item.empty or false end}
                if work then item.components.tool={CanDoAction=function(_,a) return a==work end} end
                return item
            end
            function plant(name,product)
                local item=entity(name)
                item.components.pickable={product=product,CanBePicked=function() return not item.picked end}
                return item
            end
            function loose(name)
                local item=entity(name)
                item.components.inventoryitem={canbepickedup=true}
                return item
            end
            function reset() pushed={}; bot.components.locomotor.bufferedaction=nil; bot.bufferedaction=nil; bot.busy=false end
            TheSim={FindEntities=function(_,x,y,z,radius,must,cant)
                assert(x==0 and y==0 and z==0 and radius==12 and must==nil and type(cant)=='table')
                return found
            end}
            TheWorld={state={phase='day'},Map={IsPassableAtPoint=function() return true end,
                IsGroundTargetBlocked=function() return false end}}
            bot.LightWatcher={GetLightValue=function() return lightvalue or 0 end}
        ''')
        self.lua.globals().Survival = self.lua.execute(
            (ROOT / 'scripts/ai_survival.lua').read_text(encoding='utf-8'))

    def run_lua(self, source):
        self.lua.execute(source)

    def test_gather_pick_pickup_and_guid(self):
        self.run_lua('''
            local grass=plant('grass','cutgrass'); grass.GUID=501; found={grass}
            assert(Survival.Apply(bot,{action='gather',target_guid=501}))
            assert(pushed[1].action==ACTIONS.PICK and pushed[1].target==grass)
            reset(); grass.picked=true
            assert(not Survival.Apply(bot,{action='pick',target='grass'}))
            local twig=loose('twigs'); found={twig}
            assert(Survival.Apply(bot,{type='pickup',target='twigs'}))
            assert(pushed[1].action==ACTIONS.PICKUP)
            reset(); twig.components.inventoryitem.owner=entity('other')
            assert(not Survival.Apply(bot,{action='gather',target='twigs'}))
        ''')

    def test_eat_valid_owned_food_using_buffered_action(self):
        self.run_lua('''
            local bad=food('monstermeat',18,-20,-15)
            local invalid=food('inedible'); invalid.inedible=true
            local disliked=food('disliked'); disliked.disliked=true
            local berry=food('berries'); owned={bad,invalid,disliked,berry}
            bot.components.hunger.current=10
            assert(Survival.Tick(bot))
            assert(#pushed==1 and pushed[1].action==ACTIONS.EAT and pushed[1].invobject==berry)
            assert(bot.components.hunger.current==10, 'must not grant hunger directly')
            reset(); assert(not Survival.Apply(bot,{action='eat',item='monstermeat'}))
            assert(not Survival.Apply(bot,{action='eat',item='groundfood'}))
        ''')

    def test_no_restarting_busy_or_walking_actions(self):
        self.run_lua('''
            local grass=plant('grass','cutgrass'); found={grass}
            for _, mode in ipairs({'busy','bufferedaction','locomotor'}) do
                reset()
                if mode=='busy' then bot.busy=true
                elseif mode=='bufferedaction' then bot.bufferedaction={}
                else bot.components.locomotor.bufferedaction={} end
                assert(not Survival.Tick(bot))
                assert(not Survival.Apply(bot,{action='gather',target='grass'}))
                assert(#pushed==0)
            end
            reset(); assert(Survival.Tick(bot)); assert(not Survival.Tick(bot)); assert(#pushed==1)
        ''')

    def test_torch_requires_real_known_recipe_ingredients(self):
        self.run_lua('''
            TheWorld.state.phase='night'; recipes.torch={name='torch'}
            assert(not Survival.Tick(bot)); assert(#crafted==0)
            recipes.torch.available=true; recipes.torch.unknown=true
            assert(not Survival.Tick(bot)); assert(#crafted==0)
            recipes.torch.unknown=false
            assert(Survival.Tick(bot)); assert(crafted[1]=='torch')
            assert(#owned==0, 'module must not spawn the crafting output')
            bot.components.builder.freebuildmode=true
            assert(not Survival.Apply(bot,{action='craft',recipe='torch'}))
        ''')

    def test_dusk_equips_torch_and_rejects_empty_or_restricted_items(self):
        self.run_lua('''
            TheWorld.state.phase='dusk'
            local torch=equipment('torch'); owned={torch}
            assert(Survival.Tick(bot)); assert(equipped.hands==torch)
            assert(not Survival.Tick(bot))
            equipped.hands=nil; torch.empty=true
            assert(not Survival.Apply(bot,{action='equip',item='torch'}))
            torch.empty=false; torch.restricted=true
            assert(not Survival.Apply(bot,{action='equip',item='torch'}))
        ''')

    def test_collects_torch_materials_and_caps_supplies(self):
        self.run_lua('''
            TheWorld.state.phase='dusk'
            local grass=plant('grass','cutgrass'); found={grass}
            assert(Survival.Tick(bot)); assert(pushed[1].target==grass)
            reset(); local twigs=loose('twigs'); found={grass,twigs}
            local g=loose('cutgrass'); g.components.stackable={StackSize=function() return 4 end}
            owned={g}; assert(Survival.Tick(bot)); assert(pushed[1].target==twigs)
            reset(); local t=loose('twigs'); t.components.stackable={StackSize=function() return 4 end}
            local f=food('berries'); f.components.stackable={StackSize=function() return 6 end}
            owned={g,t,f}; TheWorld.state.phase='day'; found={grass,twigs,plant('berrybush','berries')}
            assert(not Survival.Tick(bot)); assert(#pushed==0)
        ''')

    def test_full_inventory_does_not_loop_gathering(self):
        self.run_lua('''
            full=true; found={plant('grass','cutgrass'),loose('twigs'),plant('berrybush','berries')}
            assert(not Survival.Tick(bot)); assert(#pushed==0)
        ''')

    def test_chop_mine_require_owned_correct_equipped_tool(self):
        self.run_lua('''
            local tree=entity('evergreen'); found={tree}
            tree.components.workable={CanBeWorked=function() return true end,GetWorkAction=function() return ACTIONS.CHOP end}
            assert(not Survival.Apply(bot,{action='chop',target='evergreen'}))
            local pick=equipment('pickaxe',ACTIONS.MINE); owned={pick}
            assert(not Survival.Apply(bot,{action='chop',target='evergreen'}))
            local axe=equipment('axe',ACTIONS.CHOP); owned={pick,axe}
            assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
            assert(pushed[1].invobject==axe and pushed[1].action==ACTIONS.CHOP)
            reset(); tree.prefab='rock1'; tree.components.workable.GetWorkAction=function() return ACTIONS.MINE end
            assert(Survival.Apply(bot,{action='mine',target='rock1'}))
            assert(pushed[1].invobject==pick and equipped.hands==pick)
        ''')

    def test_chop_and_mine_continue_only_after_buffered_work_finishes(self):
        self.run_lua('''
            for _, work in ipairs({ACTIONS.CHOP,ACTIONS.MINE}) do
                reset()
                local target=entity('resource')
                local remaining=3
                target.components.workable={CanBeWorked=function() return remaining>0 end,
                    GetWorkAction=function() return work end}
                local tool=equipment('tool',work); owned={tool}; found={target}
                local command=work==ACTIONS.CHOP and 'chop' or 'mine'
                assert(Survival.Apply(bot,{action=command,target='resource'}))
                assert(not Survival.Tick(bot) and #pushed==1, 'active work must not be overwritten')
                assert(not Survival.Apply(bot,{action=command,target='resource'}))
                for hit=2,3 do
                    remaining=remaining-1
                    reset()
                    assert(Survival.Tick(bot), 'idle bot must continue validated work')
                    assert(#pushed==1 and pushed[1].target==target)
                    assert(pushed[1].action==work and pushed[1].invobject==tool)
                end
                remaining=0; reset()
                assert(not Survival.Tick(bot) and #pushed==0, 'depleted target must stop')
                remaining=3
                assert(not Survival.Tick(bot), 'depleted intent must not revive')
            end
        ''')

    def test_tick_can_defer_work_without_deferring_survival_needs(self):
        self.run_lua('''
            local tree=entity('evergreen'); found={tree}
            tree.components.workable={CanBeWorked=function() return true end,
                GetWorkAction=function() return ACTIONS.CHOP end}
            local axe=equipment('axe',ACTIONS.CHOP); owned={axe}
            assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
            reset()
            assert(not Survival.Tick(bot,true) and #pushed==0, 'queued commands must get an idle slot')
            assert(Survival.Tick(bot), 'deferral must preserve work intent')
            reset(); bot.components.hunger.current=1; owned={axe,food('berries')}
            assert(Survival.Tick(bot,true) and pushed[1].action==ACTIONS.EAT)
            reset(); bot.components.hunger.current=100
            assert(not Survival.Tick(bot), 'urgent eating must cancel work intent')
        ''')

    def test_continuation_clears_invalid_targets_and_tools_without_reviving(self):
        self.run_lua('''
            local cases={
                function(target,tool) target.removed=true end,
                function(target,tool) target.components.workable=nil end,
                function(target,tool) target.tags.fire=true end,
                function(target,tool) target.x=13 end,
                function(target,tool) target.components.workable.GetWorkAction=function() return ACTIONS.MINE end end,
                function(target,tool) tool.removed=true end,
                function(target,tool) tool.empty=true end,
                function(target,tool) tool.restricted=true end,
                function(target,tool) tool.components.finiteuses={GetUses=function() return 0 end} end,
                function(target,tool) tool.components.tool=nil end,
                function(target,tool) owned={} end,
                function(target,tool) equipped.hands=nil end,
            }
            for _, invalidate in ipairs(cases) do
                reset()
                local tree=entity('evergreen')
                local workable={CanBeWorked=function() return true end,
                    GetWorkAction=function() return ACTIONS.CHOP end}
                tree.components.workable=workable
                local axe=equipment('axe',ACTIONS.CHOP); owned={axe}; found={tree}
                assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
                reset(); invalidate(tree,axe)
                assert(not Survival.Tick(bot) and #pushed==0, 'invalid work must stop')
                tree.removed=false; tree.tags={}; tree.x=1; tree.components.workable=workable
                workable.GetWorkAction=function() return ACTIONS.CHOP end
                axe.removed=false; axe.empty=false; axe.restricted=false; axe.components.finiteuses=nil
                axe.components.tool={CanDoAction=function(_,action) return action==ACTIONS.CHOP end}
                owned={axe}; equipped.hands=axe
                assert(not Survival.Tick(bot), 'cleared intent must not revive')
            end
        ''')

    def test_normal_survival_gathering_precedes_then_resumes_work(self):
        self.run_lua('''
            local tree=entity('evergreen')
            tree.components.workable={CanBeWorked=function() return true end,
                GetWorkAction=function() return ACTIONS.CHOP end}
            local axe=equipment('axe',ACTIONS.CHOP); owned={axe}; found={tree}
            assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
            reset(); local grass=plant('grass','cutgrass'); found={tree,grass}
            assert(Survival.Tick(bot) and pushed[1].target==grass)
            reset(); grass.picked=true
            local berries=plant('berrybush','berries'); found={tree,grass,berries}
            assert(Survival.Tick(bot) and pushed[1].target==berries)
            reset(); berries.picked=true
            assert(Survival.Tick(bot) and pushed[1].target==tree)
        ''')

    def test_explicit_idle_commands_replace_retained_work(self):
        self.run_lua('''
            local tree=entity('evergreen')
            tree.components.workable={CanBeWorked=function() return true end,
                GetWorkAction=function() return ACTIONS.CHOP end}
            local rock=entity('rock1')
            rock.components.workable={CanBeWorked=function() return true end,
                GetWorkAction=function() return ACTIONS.MINE end}
            local axe=equipment('axe',ACTIONS.CHOP); local pick=equipment('pickaxe',ACTIONS.MINE)
            owned={axe,pick}; found={tree,rock}
            assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
            reset(); assert(Survival.Apply(bot,{action='mine',target='rock1'}))
            reset(); assert(Survival.Tick(bot) and pushed[1].target==rock)
            for _, command in ipairs({'gather','eat','craft','equip'}) do
                reset(); owned={axe,pick}; found={tree,rock}
                assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
                reset()
                assert(not Survival.Apply(bot,{action='attack'}))
                assert(Survival.Tick(bot), 'rejected commands must preserve intent')
                reset()
                local grass=plant('grass','cutgrass'); found={tree,grass}
                local berry=food('berries'); owned={axe,pick,berry}
                recipes.axe={name='axe',available=true}
                local action={action=command,target='grass',item='berries'}
                if command=='craft' then action.recipe='axe' end
                if command=='equip' then action.item='pickaxe' end
                assert(Survival.Apply(bot,action))
                reset(); grass.picked=true
                if command=='equip' then equipped.hands=axe end
                assert(not Survival.Tick(bot), 'successful explicit command must clear prior work')
            end
        ''')

    def test_danger_and_night_cancel_retained_work(self):
        self.run_lua('''
            for _, reason in ipairs({'danger','blocked_escape','night','dusk'}) do
                reset(); TheWorld.state.phase='day'
                TheWorld.Map.IsPassableAtPoint=function() return true end
                local tree=entity('evergreen')
                tree.components.workable={CanBeWorked=function() return true end,
                    GetWorkAction=function() return ACTIONS.CHOP end}
                local axe=equipment('axe',ACTIONS.CHOP); owned={axe}; found={tree}
                assert(Survival.Apply(bot,{action='chop',target='evergreen'}))
                reset()
                if reason=='danger' or reason=='blocked_escape' then
                    local hound=entity('hound',2,0); hound.components.combat={target=bot}; found={tree,hound}
                    if reason=='blocked_escape' then TheWorld.Map.IsPassableAtPoint=function() return false end end
                    local dispatched=Survival.Tick(bot)
                    if reason=='danger' then assert(dispatched and pushed[1].action==ACTIONS.WALKTO)
                    else assert(not dispatched and #pushed==0) end
                else
                    TheWorld.state.phase=reason
                    if reason=='dusk' then owned={axe,equipment('torch')} end
                    local dispatched=Survival.Tick(bot)
                    if reason=='dusk' then assert(dispatched and equipped.hands.prefab=='torch')
                    else assert(not dispatched and #pushed==0) end
                end
                reset(); TheWorld.state.phase='day'; found={tree}; equipped.hands=axe
                assert(not Survival.Tick(bot), 'survival override must cancel work intent')
            end
        ''')

    def test_imminent_threat_flees_with_passable_buffered_walk(self):
        self.run_lua('''
            local hound=entity('hound',2,0); hound.components.combat={target=bot}; found={hound}
            bot.components.hunger.current=1; owned={food('berries')}
            assert(Survival.Tick(bot))
            assert(pushed[1].action==ACTIONS.WALKTO and pushed[1].pos.x<0)
            reset(); TheWorld.Map.IsPassableAtPoint=function() return false end
            assert(not Survival.Tick(bot)); assert(#pushed==0)
        ''')

    def test_observe_contains_only_serializable_primitives_and_resource_contracts(self):
        self.run_lua('''
            local berries=food('berries'); berries.components.stackable={StackSize=function() return 3 end}
            local torch=equipment('torch'); owned={berries,torch}; equipped.hands=torch
            local grass=plant('grass','cutgrass'); grass.GUID=42
            local hound=entity('hound',3,0); hound.components.combat={target=bot}
            found={grass,hound}; recipes.torch={name='torch',available=true}; lightvalue=.2
            local o=Survival.Observe(bot)
            assert(o.health.current==100 and o.hunger.max==150 and o.sanity.current==150)
            assert(o.inventory.berries==3 and o.equipment.hands=='torch')
            assert(o.light.in_light and o.light.torch_equipped and o.light.value==.2)
            assert(o.nearby[1].guid==42 and o.nearby[1].actions[1]=='pick')
            assert(o.threats[1].prefab=='hound' and o.craftable[1]=='torch')
            local function primitive(value)
                if type(value)=='table' then for k,v in pairs(value) do primitive(k); primitive(v) end
                else assert(type(value)=='number' or type(value)=='boolean' or type(value)=='string') end
            end
            primitive(o)
        ''')

    def test_day_gathers_food_after_torch_materials_are_stocked(self):
        self.run_lua('''
            local g=loose('cutgrass'); g.components.stackable={StackSize=function() return 4 end}
            local t=loose('twigs'); t.components.stackable={StackSize=function() return 4 end}
            owned={g,t}; local bush=plant('berrybush','berries'); found={bush}
            assert(Survival.Tick(bot)); assert(pushed[1].target==bush and pushed[1].action==ACTIONS.PICK)
            reset(); bot.components.health.IsDead=function() return true end
            assert(not Survival.Tick(bot))
            assert(not Survival.Apply(bot,{action='gather',target='berrybush'}))
        ''')

    def test_crafting_rejects_placement_recipes_and_unknown_commands(self):
        self.run_lua('''
            recipes.campfire={name='campfire',available=true,placer='campfire_placer'}
            assert(not Survival.Apply(bot,{action='craft',recipe='campfire'}))
            assert(not Survival.Apply(bot,{action='craft',recipe='nonexistent'}))
            assert(not Survival.Apply(bot,{action='attack',target='player'}))
            assert(not Survival.Apply(bot,{action='gather'}))
            assert(not Survival.Apply(bot,nil))
            bot.tags.playerghost=true; assert(not Survival.Tick(bot))
        ''')


if __name__ == '__main__':
    unittest.main()
