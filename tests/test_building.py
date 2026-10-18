"""Building/prototyping contracts for the real Lua survival module."""
import unittest
from tests import test_survival


class BuildingTest(unittest.TestCase):
    def setUp(self):
        fixture = test_survival.SurvivalTest()
        fixture.setUp()
        self.lua = fixture.lua
        self.lua.execute('''
            local b=bot.components.builder
            buffers,menu_calls,placed={},0,0
            bot.components.inventory.IsOpenedBy=function(_,actor) return actor==bot end
            b.CanLearn=function(_,name) return not recipes[name].restricted end
            b.accessible_tech_trees={SCIENCE=1}
            function CanPrototypeRecipe(level,trees) return (level.SCIENCE or 0)<=(trees.SCIENCE or 0) end
            b.IsBuildBuffered=function(_,name) return buffers[name]==true end
            b.BufferBuild=function(_,name)
                assert(not buffers[name], 'buffering twice spends ingredients twice')
                assert(recipes[name].available)
                buffers[name]=true; recipes[name].available=false
            end
            b.MakeRecipeFromMenu=function(_,recipe)
                assert(recipe.placer==nil)
                menu_calls=menu_calls+1
                bot.components.locomotor.bufferedaction={action='BUILD'}
            end
            b.MakeRecipeAtPoint=function(_,recipe,point,rot)
                assert(buffers[recipe.name] and point and rot==0)
                assert(TheWorld.Map:CanDeployRecipeAtPoint(point,recipe,rot,bot))
                placed=placed+1
                bot.components.locomotor.bufferedaction={action='BUILD'}
            end
            TheWorld.Map.CanDeployRecipeAtPoint=function() return not blocked end
        ''')

    def test_placement_buffers_real_materials_then_dispatches(self):
        self.lua.execute('''
            recipes.researchlab={name='researchlab',placer='researchlab_placer',available=true,level={SCIENCE=0}}
            assert(Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(buffers.researchlab and placed==1)
            assert(not recipes.researchlab.available)
            reset()
            assert(Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(placed==2, 'buffered retry must work without paying again')
        ''')

    def test_blocked_placement_does_not_consume_materials(self):
        self.lua.execute('''
            recipes.researchlab={name='researchlab',placer='researchlab_placer',available=true,level={SCIENCE=0}}
            blocked=true
            assert(not Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(not buffers.researchlab and placed==0 and recipes.researchlab.available)
        ''')

    def test_nearby_prototyping_uses_menu_and_respects_character_gates(self):
        self.lua.execute('''
            recipes.backpack={name='backpack',available=true,unknown=true,level={SCIENCE=1}}
            assert(Survival.Apply(bot,{action='craft',recipe='backpack'}))
            assert(menu_calls==1)
            reset(); recipes.backpack.restricted=true
            assert(not Survival.Apply(bot,{action='craft',recipe='backpack'}))
            recipes.backpack.restricted=false; bot.components.builder.accessible_tech_trees.SCIENCE=0
            assert(not Survival.Apply(bot,{action='craft',recipe='backpack'}))
            assert(menu_calls==1)
        ''')

    def test_no_freebuild_no_missing_materials_no_closed_inventory(self):
        self.lua.execute('''
            recipes.campfire={name='campfire',placer='campfire_placer',available=true,level={}}
            bot.components.builder.freebuildmode=true
            assert(not Survival.Apply(bot,{action='build',recipe='campfire'}))
            bot.components.builder.freebuildmode=false; recipes.campfire.available=false
            assert(not Survival.Apply(bot,{action='build',recipe='campfire'}))
            recipes.campfire.available=true
            bot.components.inventory.IsOpenedBy=function() return false end
            assert(not Survival.Apply(bot,{action='build',recipe='campfire'}))
            assert(placed==0)
        ''')


if __name__ == '__main__':
    unittest.main()
