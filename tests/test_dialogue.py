"""Exercise dialogue state in Lua 5.1 without loading the game or providers."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class DialogueTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().D = self.lua.execute(
            (ROOT / "scripts/ai_dialogue.lua").read_text(encoding="utf-8"))
        self.lua.execute('''
            bot = {}
            human = {userid='KU_human',name='Player'}
            function obs(amount, blocked)
                return {inventory={goldnugget=amount or 0},
                    progression={goal='researchlab',missing={goldnugget=1},blocked=blocked ~= false}}
            end
            function receive(text, now) return D.Receive(bot,human,text,now or 0) end
        ''')

    def run_lua(self, source):
        self.lua.execute(source)

    def test_validate_metadata_cooldown_and_bounded_history(self):
        self.run_lua('''
            assert(not D.Receive(bot,nil,'hi',0))
            assert(not D.Receive(bot,{userid=7,name='x'},'hi',0))
            assert(not D.Receive(bot,{userid='',name='x'},'hi',0))
            assert(not receive(string.char(0,1,127),0))
            assert(receive('你好',0))
            assert(not receive('spam',1.99))
            assert(receive('next',2))
            for i=1,40 do assert(receive('line'..i,i*2+2)) end
            local c=D.Observe(bot,100)
            assert(#c.history==12 and c.pending_message.text=='line40')
            c.history[1].text='tampered'; c.pending_message.text='tampered'
            assert(D.Observe(bot,100).pending_message.text=='line40')
            assert(D.Observe(bot,100).history[1].text~='tampered')
            for i=1,40 do
                assert(D.Receive(bot,{userid='user'..i,name='x'},'hi',200))
            end
            assert(#bot._ai_dialogue.speakers==16)
        ''')

    def test_utf8_is_sanitized_and_truncated_at_codepoint_boundaries(self):
        self.run_lua('''
            local raw=string.char(0,31,127,194,128,255,192,175,237,160,128,244,144,128,128)
            assert(receive(raw..string.rep('金',200),0))
            local text=D.Observe(bot,0).pending_message.text
            assert(#text==384 and text==string.rep('金',128))
            assert(receive(string.rep('a',383)..'金',2))
            assert(D.Observe(bot,2).pending_message.text==string.rep('a',383))
            assert(receive('a'..string.char(226,130)..'b',4))
            assert(D.Observe(bot,4).pending_message.text=='ab')
        ''')

    def test_inflight_snapshot_preserves_new_messages_and_request_cooldown(self):
        self.run_lua('''
            assert(receive('old suggestion',0)); assert(D.Due(bot,0))
            local rev=D.Begin(bot,0)
            assert(rev and not D.Due(bot,20) and D.Begin(bot,20)==nil)
            assert(receive('new suggestion',2))
            assert(D.End(bot,rev,{action='explore',try_advice=true,message='好的'},obs(),3)=='好的')
            assert(D.Observe(bot,3).pending_message.text=='new suggestion')
            assert(D.Observe(bot,3).trial.text=='old suggestion')
            assert(not D.Due(bot,7.99) and D.Due(bot,8))
            local nextrev=D.Begin(bot,8)
            assert(D.End(bot,rev,{message='stale'},obs(),9)==nil)
            assert(D.End(bot,nextrev,{message='received'},obs(),9)=='received')
            assert(D.Observe(bot,9).pending_message==nil)
        ''')

    def test_failed_requests_preserve_pending_and_stale_retries_are_ignored(self):
        self.run_lua('''
            receive('help',0)
            local rev=D.Begin(bot,0)
            assert(D.End(bot,rev,nil,obs(),1)==nil)
            assert(D.Observe(bot,1).pending_message.text=='help')
            assert(not D.Due(bot,7) and D.Due(bot,8))
            local retry=D.Begin(bot,8)
            assert(retry~=rev)
            assert(D.End(bot,rev,{message='late'},obs(),9)==nil)
            assert(not D.Due(bot,100))
            assert(D.End(bot,retry,{error='timeout'},obs(),10)==nil)
            assert(D.Observe(bot,10).pending_message.text=='help')
            retry=D.Begin(bot,16)
            D.End(bot,retry,{},obs(),17)
            assert(D.Observe(bot,17).pending_message.text=='help')
        ''')

    def test_observed_trials_ignore_model_success_and_dispatch_claims(self):
        self.run_lua('''
            receive('try mining',0)
            local token=D.Begin(bot,0)
            D.End(bot,token,{action='mine',try_advice=true,success=true,confidence=1,dispatched=true},obs(),1)
            local c=D.Observe(bot,1)
            assert(c.trial.status=='provisional' and c.trial.untrusted and c.trial.dispatched==true)
            assert(c.player_advice.untrusted and c.policy.history_untrusted)
            D.Tick(bot,obs(1),5)
            assert(D.Observe(bot,5).trial.status=='provisional')
            local feedback=D.Tick(bot,obs(1),11)
            assert(feedback and string.find(feedback,'进展',1,true))
            assert(D.Tick(bot,obs(1),12)==nil)
            assert(D.Observe(bot,11).trial.status=='observed_progress')
            receive('another idea',20)
            token=D.Begin(bot,20)
            D.End(bot,token,{action='mine',message='worked',try_advice=true,dispatched=false,success=true},obs(),21)
            assert(D.Observe(bot,21).trial.dispatched==false)
            D.Tick(bot,obs(),95)
            assert(D.Observe(bot,95).trial.status=='provisional')
            local timeout=D.Tick(bot,obs(),96)
            assert(timeout and string.find(timeout,'不能确认',1,true))
            assert(D.Observe(bot,96).trial.status=='inconclusive')
        ''')

    def test_trials_observe_goal_outputs_not_dispatch_or_goal_claims(self):
        self.run_lua('''
            local function trial(goal)
                bot={}; receive('try this recipe',0)
                local o={inventory={},progression={goal=goal,missing={}}}
                local token=D.Begin(bot,0)
                D.End(bot,token,{action='craft',try_advice=true,dispatched=true},o,1)
                return o
            end
            for _, goal in ipairs({'axe','pickaxe','backpack'}) do
                local o=trial(goal)
                for i=1,100 do o.inventory['filler'..i]=1 end
                o.inventory[goal]=1; o.progression.goal='logs'
                assert(D.Tick(bot,o,11))
                assert(D.Observe(bot,11).trial.status=='observed_progress')
            end
            local o=trial('equip_backpack')
            o.inventory.backpack=1
            D.Tick(bot,o,11)
            assert(D.Observe(bot,11).trial.status=='provisional')
            o.inventory.backpack=0; o.equipment={body={prefab='backpack'}}
            assert(D.Tick(bot,o,12))
            assert(D.Observe(bot,12).trial.status=='observed_progress')
            o=trial('researchlab')
            o.progression.goal='backpack'; o.built={researchlab=true}
            D.Tick(bot,o,11)
            assert(D.Observe(bot,11).trial.status=='provisional')
            o.structures={{prefab='researchlab',guid=77}}
            assert(D.Tick(bot,o,12))
            assert(D.Observe(bot,12).trial.status=='observed_progress')
            o=trial('axe'); o.progression.goal='logs'
            D.Tick(bot,o,11)
            assert(D.Observe(bot,11).trial.status=='provisional')
            D.Tick(bot,o,76)
            assert(D.Observe(bot,76).trial.status=='inconclusive')
        ''')

    def test_ordinary_greeting_and_say_do_not_create_trials(self):
        self.run_lua('''
            receive('hello',0)
            local token=D.Begin(bot,0)
            assert(D.End(bot,token,{action='say',message='你好'},obs(),1)=='你好')
            assert(D.Observe(bot,1).trial==nil)
            local o=obs(); o.progression.missing={}; o.progression.blocked=false
            assert(D.Tick(bot,o,76)==nil)
            receive('thanks',80)
            token=D.Begin(bot,80)
            D.End(bot,token,{message='不客气',try_advice=false},o,81)
            assert(D.Observe(bot,81).trial==nil and D.Tick(bot,o,156)==nil)
            receive('maybe explore',160)
            token=D.Begin(bot,160)
            D.End(bot,token,{action='explore',try_advice='true'},o,161)
            assert(D.Observe(bot,161).trial==nil)
        ''')

    def test_stalls_ask_specific_chinese_questions_with_help_cooldown(self):
        self.run_lua('''
            assert(D.Tick(bot,obs(),0)==nil)
            assert(D.Tick(bot,obs(),44.99)==nil)
            local question=D.Tick(bot,obs(),45)
            assert(question and string.find(question,'金子',1,true))
            assert(not D.Due(bot,45), 'proactive speech is not an API request')
            assert(D.Tick(bot,obs(),134.99)==nil)
            assert(D.Tick(bot,obs(),135))
            local o=obs(); o.progression.missing={charcoal=2}
            bot={}
            assert(D.Tick(bot,o,0)==nil)
            assert(string.find(D.Tick(bot,o,45),'木炭',1,true))
            o.progression.missing={}; bot={}
            D.Tick(bot,o,0)
            assert(string.find(D.Tick(bot,o,45),'配方',1,true))
        ''')

    def test_progress_and_goal_changes_reset_stall_and_no_shortage_does_not_ask(self):
        self.run_lua('''
            D.Tick(bot,obs(),0)
            D.Tick(bot,obs(1),40)
            assert(D.Tick(bot,obs(1),45)==nil)
            assert(D.Tick(bot,obs(1),84.99)==nil)
            assert(D.Tick(bot,obs(1),85))
            bot={}; D.Tick(bot,obs(),0)
            local o=obs(); o.progression.goal='backpack'
            assert(D.Tick(bot,o,44)==nil and D.Tick(bot,o,45)==nil)
            assert(D.Tick(bot,o,89))
            bot={}; o.progression.blocked=false; o.progression.missing={}
            D.Tick(bot,o,0); assert(D.Tick(bot,o,500)==nil)
            bot={}; o=obs(0,false)
            D.Tick(bot,o,0); assert(D.Tick(bot,o,45))
        ''')

    def test_unknown_recipe_ask_and_bounded_nested_context(self):
        self.run_lua('''
            local token=D.Begin(bot,0)
            assert(D.End(bot,token,{ask='木炭怎么弄',message='ignored'},obs(),1)=='木炭怎么弄')
            assert(D.Observe(bot,1).active_question.text=='木炭怎么弄')
            token=D.Begin(bot,8)
            assert(D.End(bot,token,{ask=true,question='金子在哪里？'},obs(),9)==nil)
            assert(D.Observe(bot,9).active_question.text=='木炭怎么弄')
            token=D.Begin(bot,91)
            assert(D.End(bot,token,{ask=true,message='金子在哪里？'},obs(),92)=='金子在哪里？')
            assert(D.Observe(bot,92).active_question.text=='金子在哪里？')
            assert(D.Observe(bot,272).active_question==nil)
            token=D.Begin(bot,96) -- Ordinary periodic think keeps the manager's cadence.
            local cycle={}; cycle.self=cycle
            assert(D.End(bot,token,{message=string.rep('金',1000),extra=cycle},obs(),97))
            local o=obs(); o.capabilities=cycle
            for i=1,100 do o.capabilities['key'..i]=string.rep('x',1000) end
            D.Tick(bot,o,20)
            local c=D.Observe(bot,20)
            assert(#c.history[#c.history].text<=384)
            local n=0; for k,v in pairs(c.capabilities) do n=n+1 end
            assert(n<=16 and string.find(c.policy.limitations,'No ignite',1,true))
            assert(c.policy.player_advice_untrusted and not c.trial)
        ''')


if __name__ == "__main__":
    unittest.main()
