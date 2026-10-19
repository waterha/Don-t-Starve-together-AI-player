"""Execute the pure scheduler in Lua 5.1; no providers, game, or network."""
from pathlib import Path
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class RequestPolicyTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.globals().P = self.lua.execute(
            (ROOT / "scripts/ai_request_policy.lua").read_text(encoding="utf-8"))

    def test_interval_clamp_and_all_reason_pairs_obey_exact_hard_cap(self):
        self.lua.execute('''
            for _, interval in ipairs({-1, 0, 4, 5, 8, 30, 120}) do
                local cap=math.max(5,interval)
                for _, first in ipairs({'chat','plan_completed','plan_failed','emergency','periodic'}) do
                    for _, second in ipairs({'chat','plan_completed','plan_failed','emergency','periodic'}) do
                        -- Human chat has a five-second floor instead of the periodic cap.
                        local gap=(second=='chat') and 5 or cap
                        local s=P.New(interval)
                        assert(s.interval==cap and P.Start(s,0,first))
                        assert(not P.Start(s,cap*2,second), 'overlapping start')
                        assert(s.metrics.requests==1)
                        P.Finish(s,1,nil)
                        assert(not P.CanStart(s,gap-.001,second))
                        assert(not P.Start(s,gap-.001,second))
                        assert(P.CanStart(s,gap,second) and P.Start(s,gap,second))
                        assert(s.metrics.requests==2)
                    end
                end
            end
            local s=P.New(30)
            assert(P.Start(s,0,'periodic')); P.Finish(s,40,nil)
            assert(P.Start(s,40,'chat'), 'interval measured between starts, not finishes')
        ''')

    def test_chat_preempts_periodic_cap_but_keeps_floor_and_backoff(self):
        self.lua.execute('''
            local s=P.New(30)
            assert(P.Start(s,0,'periodic')); P.Finish(s,2,nil)
            assert(not P.CanStart(s,4.999,'chat'), 'chat must keep a five-second floor')
            assert(P.CanStart(s,5,'chat'), 'chat must not wait the thirty-second periodic cap')
            assert(P.Start(s,5,'chat'))
            assert(not P.CanStart(s,6,'periodic'), 'a request is already in flight')
            P.Finish(s,6,'HTTP 429',20)
            assert(not P.CanStart(s,25.999,'chat'), 'chat must honor the rate-limit cooldown')
            assert(P.CanStart(s,26,'chat'))
            local auth=P.New(5)
            auth.blocked_auth=true
            assert(not P.CanStart(auth,1000,'chat'), 'authentication pause blocks chat too')
        ''')

    def test_pending_priorities_preserve_oldest_age_and_take_does_not_start(self):
        self.lua.execute('''
            local s=P.New(10)
            assert(P.Start(s,0,'periodic'))
            for i,reason in ipairs({'periodic','plan_completed','plan_failed','emergency','chat'}) do
                assert(P.Pending(s,reason,i))
                assert(s.pending_reason==reason and s.pending_at==1)
            end
            P.Pending(s,'chat',8); P.Pending(s,'periodic',9)
            assert(s.pending_reason=='chat' and s.pending_at==1)
            assert(P.Take(s,4)==nil and s.pending_reason=='chat')
            P.Finish(s,3,nil)
            assert(P.Take(s,4.999)==nil)
            local reason,wait=P.Take(s,5)
            assert(reason=='chat' and wait==4000 and s.pending_reason==nil)
            assert(not s.inflight and s.metrics.requests==1)
            assert(P.Take(s,5)==nil)
            assert(s.metrics.schedule_wait_count==1 and s.metrics.schedule_wait_ms==4000)
            assert(P.Start(s,5,reason))
            P.Pending(s,'periodic',6); P.Finish(s,6.5,nil)
            reason,wait=P.Take(s,15)
            assert(reason=='periodic' and wait==9000)
            assert(s.metrics.schedule_wait_count==2)
        ''')

    def test_rate_limit_backoff_doubles_and_caps_with_exact_eligibility(self):
        self.lua.execute('''
            local s=P.New(5); local now=0
            for _,delay in ipairs({15,30,60,120,120,120}) do
                assert(P.Start(s,now,'chat')); P.Finish(s,now+1,'upstream returned HTTP 429')
                assert(s.retry_at==now+1+delay)
                assert(not P.CanStart(s,s.retry_at-.001,'chat'))
                assert(P.CanStart(s,s.retry_at,'chat'))
                now=s.retry_at
            end
            assert(s.metrics.requests==6)
        ''')

    def test_retry_after_validation_clamping_and_prior_cooldown_preservation(self):
        self.lua.execute('''
            for _,case in ipairs({{0,15},{2,15},{45,45},{'90',90},{9999,300}}) do
                local s=P.New(5)
                P.Finish(s,10,'HTTP 429',case[1])
                assert(s.retry_at==10+case[2])
                assert(not P.CanStart(s,s.retry_at-.001,'periodic'))
                assert(P.CanStart(s,s.retry_at,'periodic'))
            end
            for _,bad in ipairs({'bad',-1,math.huge,0/0}) do
                local s=P.New(5); P.Finish(s,0,429,bad)
                assert(s.retry_at==15)
            end
            local s=P.New(5); P.Finish(s,0,429,300)
            P.Finish(s,1,'timeout')
            P.Finish(s,2,'HTTP 429',15)
            assert(s.retry_at==300 and s.metrics.requests==0)
            assert(not P.Start(s,299.999,'chat') and P.Start(s,300,'chat'))
        ''')

    def test_transient_backoff_is_separate_and_success_resets_both(self):
        self.lua.execute('''
            local s=P.New(5); local now=0
            for _,delay in ipairs({5,10,20,40,60,60}) do
                assert(P.Start(s,now,'periodic'))
                P.Finish(s,now+1,'timeout')
                assert(s.retry_at==now+1+delay)
                assert(not P.CanStart(s,s.retry_at-.001,'periodic'))
                assert(P.CanStart(s,s.retry_at,'periodic'))
                now=s.retry_at
            end
            P.Start(s,now,'chat'); P.Finish(s,now+1,429)
            assert(s.retry_at==now+16, 'rate and generic counters must be separate')
            now=s.retry_at; P.Start(s,now,'chat'); P.Finish(s,now+1,nil)
            assert(s.retry_at==0 and s.rate_failures==0 and s.transient_failures==0)
            assert(not P.CanStart(s,now+4.999,'chat'))
            now=now+5; assert(P.Start(s,now,'chat')); P.Finish(s,now+1,'timeout')
            assert(s.retry_at==now+6)
            now=s.retry_at; P.Start(s,now,'chat'); P.Finish(s,now+1,429)
            assert(s.retry_at==now+16)
        ''')

    def test_auth_block_lasts_until_new_state_including_selection_errors(self):
        self.lua.execute('''
            for _,err in ipairs({401,'upstream returned HTTP 401','invalid api_key','missing API key'}) do
                local s=P.New(30)
                P.Finish(s,0,err)
                P.Pending(s,'chat',1)
                assert(s.blocked_auth and not P.CanStart(s,1e9,'chat'))
                assert(not P.Start(s,1e9,'periodic') and P.Take(s,1e9)==nil)
                assert(s.metrics.requests==0 and s.metrics.model_duration_count==0)
                P.Finish(s,2,'timeout'); P.Finish(s,3,nil)
                assert(s.blocked_auth and not P.CanStart(s,1e9,'chat'))
                assert(P.CanStart(P.New(30),0,'chat'))
            end
            local s=P.New(5); P.Start(s,0,'chat'); P.Finish(s,1,'HTTP 401')
            assert(not s.inflight and s.metrics.requests==1)
            assert(s.metrics.model_duration_count==1)
        ''')

    def test_metrics_are_numeric_latest_only_and_bad_inputs_do_not_start(self):
        self.lua.execute('''
            for _,bad in ipairs({math.huge,-math.huge,0/0,'garbage'}) do
                assert(P.New(bad).interval==5)
                local s=P.New(5)
                assert(not P.Start(s,bad,'chat') and not P.Pending(s,'chat',bad))
                assert(not P.Finish(s,bad,'timeout'))
            end
            local s=P.New(5)
            assert(not P.Start(s,0,'unknown') and not P.Pending(s,'unknown',0))
            P.Start(s,0,'chat'); P.Finish(s,1.25,'opaque error payload')
            assert(s.metrics.model_duration_ms==1250)
            assert(s.metrics.model_duration_count==1 and s.metrics.requests==1)
            P.Start(s,6.25,'chat'); P.Finish(s,6.5,nil)
            assert(s.metrics.model_duration_ms==250 and s.metrics.model_duration_count==2)
            assert(s.metrics.requests==2)
            for _,value in pairs(s.metrics) do
                assert(type(value)=='number' and value==value and value>=0 and value<math.huge)
            end
            assert(s.err==nil and s.error==nil)
        ''')


if __name__ == '__main__':
    unittest.main()
