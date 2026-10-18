"""Light timing through the real survival module, with engine fixtures only."""
import unittest
from tests import test_survival as fixture_module


class LightTimingTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SurvivalTest()
        self.fixture.setUp()
        self.lua = self.fixture.lua

    def test_bright_dusk_does_not_craft_or_equip_torch(self):
        self.lua.execute('''
            TheWorld.state.phase='dusk'; lightvalue=.5
            recipes.torch={name='torch',available=true}
            Survival.Tick(bot)
            assert(#crafted==0, 'bright dusk consumed torch ingredients')
            owned={equipment('torch')}; reset()
            Survival.Tick(bot)
            assert(not equipped.hands, 'bright dusk equipped a burning torch')
        ''')

    def test_lit_night_does_not_craft_or_equip_torch(self):
        self.lua.execute('''
            TheWorld.state.phase='night'; lightvalue=.5
            recipes.torch={name='torch',available=true}
            Survival.Tick(bot)
            assert(#crafted==0, 'existing night light was ignored when crafting')
            owned={equipment('torch')}; reset()
            Survival.Tick(bot)
            assert(not equipped.hands, 'existing night light was ignored when equipping')
        ''')

    def test_model_cannot_bypass_bright_light_torch_policy(self):
        self.lua.execute('''
            TheWorld.state.phase='dusk'; lightvalue=.5
            recipes.torch={name='torch',available=true}
            assert(not Survival.Apply(bot,{action='craft',recipe='torch'}))
            owned={equipment('torch')}
            assert(not Survival.Apply(bot,{action='equip',item='torch'}))
            assert(#crafted==0 and not equipped.hands)
        ''')

    def test_native_light_state_overrides_numeric_threshold(self):
        self.lua.execute('''
            TheWorld.state.phase='night'; lightvalue=.06
            bot.LightWatcher.IsInLight=function() return true end
            recipes.torch={name='torch',available=true}
            Survival.Tick(bot)
            assert(#crafted==0)
            assert(Survival.Observe(bot).light.in_light)
        ''')

    def test_actually_dark_dusk_still_uses_owned_torch_without_duplicate_crafting(self):
        self.lua.execute('''
            TheWorld.state.phase='dusk'; lightvalue=0
            local torch=equipment('torch'); owned={torch}
            recipes.torch={name='torch',available=true}
            assert(not Survival.Apply(bot,{action='craft',recipe='torch'}))
            assert(Survival.Tick(bot) and equipped.hands==torch)
            lightvalue=.8; reset()
            Survival.Tick(bot)
            assert(equipped.hands==torch and #crafted==0)
        ''')

    def test_dark_night_still_equips_or_crafts_emergency_light(self):
        self.lua.execute('''
            TheWorld.state.phase='night'; lightvalue=0
            local torch=equipment('torch'); owned={torch}
            assert(Survival.Tick(bot) and equipped.hands==torch)
            reset(); owned={}; equipped.hands=nil
            recipes.torch={name='torch',available=true}
            assert(Survival.Tick(bot) and crafted[1]=='torch')
        ''')


if __name__ == '__main__':
    unittest.main()
