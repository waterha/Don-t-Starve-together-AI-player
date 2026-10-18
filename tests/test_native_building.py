"""Native DST builder contracts; no proprietary method bodies are stored here."""
import os
from pathlib import Path
import re
import unittest
import zipfile

from tests import test_building as building_fixture


DEFAULT_ARCHIVE = Path(
    r"E:\WeGameApps\rail_apps\饥荒：联机版(2000004)\data\databundles\scripts.zip"
)


def native_methods(source):
    """Keep complete top-level methods, not nested function/end fragments."""
    methods = []
    for name in (
        'IsBuildBuffered', 'SetBuildBuffered', 'MakeRecipeFromMenu',
        'MakeRecipeAtPoint', 'BufferBuild',
    ):
        match = re.search(
            rf'^function Builder:{name}\([^\n]*\)\r?\n.*?^end\s*$',
            source, re.MULTILINE | re.DOTALL,
        )
        if match is None:
            raise AssertionError(f'Native builder method missing: {name}')
        methods.append(match.group(0))
    return '\n'.join(methods)


class NativeBuildingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        archive = Path(os.environ.get('DST_SCRIPTS_ZIP', DEFAULT_ARCHIVE))
        if not archive.is_file():
            if 'DST_SCRIPTS_ZIP' in os.environ:
                raise FileNotFoundError(f'DST_SCRIPTS_ZIP does not exist: {archive}')
            raise unittest.SkipTest('Installed DST scripts.zip unavailable; set DST_SCRIPTS_ZIP')
        with zipfile.ZipFile(archive) as bundle:
            source = bundle.read('scripts/components/builder.lua').decode('utf-8-sig')
        cls.methods = native_methods(source)

    def setUp(self):
        fixture = building_fixture.BuildingTest()
        fixture.setUp()
        self.lua = fixture.lua
        self.lua.execute('Builder = {}\n' + self.methods)
        self.lua.execute('''
            local b=bot.components.builder
            for name,method in pairs(Builder) do b[name]=method end
            b.buffered_builds={}
            b.accessible_tech_trees_no_temp={SCIENCE=1}
            b.recipes={}
            b.inst=bot
            bot.replica={builder={SetIsBuildBuffered=function() end}}
            b.KnowsRecipe=function(_,recipe)
                return not recipe.unknown or b.recipes[recipe.name]==true
            end
            b.CanLearn=function(_,name) return not recipes[name].restricted end
            b.CheckIngredientsForMimic=function() return false end
            b.GetIngredients=function(_,name) return {name=name},false end
            payments,activations,unlocks,dispatches=0,0,0,0
            b.RemoveIngredients=function(_,materials,name)
                assert(materials.name==name and recipes[name].available)
                payments=payments+1
                recipes[name].available=false
            end
            b.ActivateCurrentResearchMachine=function() activations=activations+1 end
            b.UnlockRecipe=function(_,name)
                b.recipes[name]=true
                unlocks=unlocks+1
            end
            b.AddRecipe=function(_,name) b.recipes[name]=true end
            function ValidateRecipeSkinRequest() return nil end
            b.MakeRecipe=function(_,recipe,point,rot,skin,onsuccess)
                assert(recipe.available or b:IsBuildBuffered(recipe.name))
                dispatches=dispatches+1
                pending_success=onsuccess
                bot.components.locomotor.bufferedaction={action='BUILD',recipe=recipe.name,pos=point}
                return true
            end
            function complete_item()
                assert(pending_success)
                local callback=pending_success
                pending_success=nil
                callback()
                reset()
            end
        ''')

    def test_unknown_nearby_prototype_unlocks_only_on_action_success(self):
        self.lua.execute('''
            recipes.backpack={name='backpack',product='backpack',available=true,
                unknown=true,level={SCIENCE=1}}
            local b=bot.components.builder
            assert(not b:KnowsRecipe(recipes.backpack))
            assert(Survival.Apply(bot,{action='craft',recipe='backpack'}))
            assert(dispatches==1 and unlocks==0 and activations==0)
            assert(not b:KnowsRecipe(recipes.backpack))
            complete_item()
            assert(unlocks==1 and activations==1 and b:KnowsRecipe(recipes.backpack))
        ''')

    def test_character_and_science_gates_prevent_native_dispatch(self):
        self.lua.execute('''
            recipes.backpack={name='backpack',product='backpack',available=true,
                unknown=true,restricted=true,level={SCIENCE=1}}
            assert(not Survival.Apply(bot,{action='craft',recipe='backpack'}))
            recipes.backpack.restricted=false
            bot.components.builder.accessible_tech_trees.SCIENCE=0
            assert(not Survival.Apply(bot,{action='craft',recipe='backpack'}))
            assert(dispatches==0 and unlocks==0 and payments==0)
        ''')

    def test_native_buffer_payment_is_idempotent_and_survives_blocked_placement(self):
        self.lua.execute('''
            recipes.researchlab={name='researchlab',placer='researchlab_placer',
                product='researchlab',available=true,level={SCIENCE=0}}
            local b=bot.components.builder
            assert(b:BufferBuild('researchlab')==nil)
            assert(b:IsBuildBuffered('researchlab') and payments==1)
            b:BufferBuild('researchlab')
            assert(payments==1, 'native repeat must not spend twice')
            blocked=true
            b:MakeRecipeAtPoint(recipes.researchlab,Vector3(2,0,0),0)
            assert(dispatches==0 and b:IsBuildBuffered('researchlab'))
            assert(not Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(payments==1)
            blocked=false
            assert(Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(payments==1 and dispatches==1)
            assert(b:IsBuildBuffered('researchlab'), 'dispatch is not DoBuild completion')
        ''')

    def test_native_placement_requires_buffer_and_prototype_buffer_unlocks(self):
        self.lua.execute('''
            recipes.researchlab={name='researchlab',placer='researchlab_placer',
                product='researchlab',available=true,unknown=true,level={SCIENCE=1}}
            local b=bot.components.builder
            b:MakeRecipeAtPoint(recipes.researchlab,Vector3(2,0,0),0)
            assert(dispatches==0 and payments==0)
            assert(Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(payments==1 and dispatches==1 and unlocks==1 and activations==1)
            assert(b:IsBuildBuffered('researchlab'))
            reset()
            assert(Survival.Apply(bot,{action='build',recipe='researchlab'}))
            assert(payments==1 and dispatches==2 and unlocks==1)
        ''')

    def test_blocked_or_closed_inventory_does_not_buffer(self):
        self.lua.execute('''
            recipes.researchlab={name='researchlab',placer='researchlab_placer',
                product='researchlab',available=true,level={SCIENCE=0}}
            blocked=true
            assert(not Survival.Apply(bot,{action='build',recipe='researchlab'}))
            blocked=false
            bot.components.inventory.IsOpenedBy=function() return false end
            assert(not Survival.Apply(bot,{action='build',recipe='researchlab'}))
            bot.components.builder:BufferBuild('researchlab')
            assert(payments==0 and dispatches==0)
            assert(not bot.components.builder:IsBuildBuffered('researchlab'))
        ''')


if __name__ == '__main__':
    unittest.main()
