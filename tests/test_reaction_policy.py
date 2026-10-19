"""Reaction-speed objective (plan B): short plans, event scheduling, chat priority, backoff, metrics."""
from pathlib import Path
import re
import unittest

from lupa.lua51 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]


class ReactionPolicyTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime()
        lua = self.lua
        lua.globals().package.path = str(ROOT / 'scripts' / '?.lua').replace('\\', '/') + ';' + lua.globals().package.path
        lua.execute('Policy = require("ai_request_policy")')

    def test_plan_completion_waits_out_the_hard_interval(self):
        self.lua.execute('''
            local p = Policy.New(30)
            assert(Policy.Start(p, 0, "periodic"))
            Policy.Finish(p, 2, nil)
            assert(not Policy.CanStart(p, 10, "periodic"), "periodic must honor the interval")
            assert(Policy.CanStart(p, 30, "periodic"))
            Policy.Pending(p, "plan_completed", 12)
            local reason, wait = Policy.Take(p, 30)
            assert(reason == "plan_completed", reason)
            assert(wait == 18000, wait)
        ''')

    def test_chat_has_priority_but_keeps_a_floor(self):
        self.lua.execute('''
            local p = Policy.New(30)
            assert(Policy.Start(p, 0, "periodic"))
            Policy.Finish(p, 1, nil)
            assert(not Policy.CanStart(p, 4, "chat"), "chat still needs a small floor")
            assert(Policy.CanStart(p, 5, "chat"), "chat must not wait a full periodic interval")
            Policy.Pending(p, "periodic", 6)
            Policy.Pending(p, "chat", 7)
            local reason = Policy.Take(p, 5)
            assert(reason == "chat", "chat must outrank periodic work")
        ''')

    def test_401_pauses_until_configuration_changes(self):
        self.lua.execute('''
            local p = Policy.New(5)
            assert(Policy.Start(p, 0, "periodic"))
            Policy.Finish(p, 1, "upstream returned HTTP 401")
            assert(p.blocked_auth)
            assert(not Policy.CanStart(p, 100000, "chat"), "auth failure must not retry forever")
        ''')

    def test_429_backoff_honors_retry_after_and_never_shrinks(self):
        self.lua.execute('''
            local p = Policy.New(5)
            assert(Policy.Start(p, 0, "periodic"))
            Policy.Finish(p, 1, "upstream returned HTTP 429", 60)
            assert(p.retry_at == 61, p.retry_at)
            assert(not Policy.CanStart(p, 60, "chat"))
            assert(Policy.Start(p, 61, "periodic"))
            Policy.Finish(p, 62, "upstream returned HTTP 429", 15)
            assert(p.retry_at == 77, p.retry_at)
        ''')

    def test_metrics_record_durations_without_errors(self):
        self.lua.execute('''
            local p = Policy.New(5)
            assert(Policy.Start(p, 10, "periodic"))
            Policy.Finish(p, 12.5, nil)
            assert(p.metrics.requests == 1)
            assert(p.metrics.model_duration_count == 1)
            assert(p.metrics.model_duration_ms == 2500, p.metrics.model_duration_ms)
            Policy.Pending(p, "periodic", 20)
            Policy.Take(p, 21)
            assert(p.metrics.schedule_wait_ms == 1000)
        ''')


class ReactionSourceTest(unittest.TestCase):
    def setUp(self):
        self.manager = (ROOT / 'scripts/ai_player_manager.lua').read_text(encoding='utf-8')
        self.prompt = re.search(r'SYSTEM_PROMPT = \[\[(.*?)\]\]', self.manager, re.S).group(1)

    def test_prompt_requests_bounded_plan(self):
        self.assertIn('"plan":[', self.prompt)
        self.assertIn('1-5 related steps', self.prompt)
        self.assertIn('dispatch is never completion', self.prompt.lower())

    def test_manager_ticks_plan_locally_and_queues_events(self):
        self.assertIn('Plan.Tick', self.manager)
        self.assertIn('QueueDecision(inst, "emergency")', self.manager)
        self.assertIn('QueueDecision(inst, status == "completed" and "plan_completed" or "plan_failed")', self.manager)
        self.assertIn('Policy.Pending(policy, "chat", now)', self.manager)
        self.assertIn('TheWorld:DoPeriodicTask(.25', self.manager)

    def test_manager_does_not_poll_the_model_every_interval_when_a_plan_runs(self):
        body = self.manager.split('function AIPlayerManager:UpdateLocal')[1].split('function AIPlayerManager:Start')[0]
        running = body.split('if inst._ai_plan then\n        -- A running plan')[1].split('return\n    end')[0]
        self.assertIn('self:TickPlan(inst)', running)
        self.assertNotIn('Think(inst, "periodic")', running)


if __name__ == '__main__':
    unittest.main()
