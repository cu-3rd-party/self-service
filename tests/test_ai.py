import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, validate_project
ROOT = Path(__file__).resolve().parents[1]

class AiTests(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.env = self.project['envs']['dev']
        self.env['ai'] = {'enabled': True, 'targetEnvPrefix': 'AI__', 'model': 'openai/gpt-4o-mini',
                          'models': ['openai/gpt-4o-mini', 'anthropic/claude-sonnet-4.5'],
                          'budgetUsd': 10, 'budgetPeriod': '30d', 'rpm': 60}
    def check(self):
        validate_project(self.project, 'telegram-bot.yaml')
    def invalid(self, **ai):
        self.env['ai'].update(ai)
        with self.assertRaises(Invalid):
            self.check()
    def test_full_and_minimal_sections(self):
        self.check()
        self.env['ai'] = {'enabled': True}
        self.check()
    def test_platform_project(self):
        validate_project(load(ROOT / 'projects/ai-gateway.yaml'), 'ai-gateway.yaml')
    def test_unknown_field(self):
        self.invalid(quota=5)
    def test_model_must_be_allowed(self):
        self.invalid(model='openai/gpt-5')
    def test_model_id_format(self):
        self.invalid(models=['gpt-4o'])
        self.invalid(models=['openai/gpt-4o-mini', 'openai/gpt-4o-mini'])
    def test_budget_and_limits(self):
        for bad in [{'budgetUsd': 0}, {'budgetUsd': '10'}, {'budgetUsd': True}, {'budgetPeriod': '1mo'}, {'rpm': 0}, {'tpm': 1.5}]:
            with self.subTest(bad):
                self.setUp()
                self.invalid(**bad)
    def test_period_requires_budget(self):
        del self.env['ai']['budgetUsd']
        with self.assertRaises(Invalid):
            self.check()
    def test_generated_credentials_cannot_be_overridden(self):
        self.env['apps']['bot']['variables']['AI__API_KEY'] = 'OTHER'
        with self.assertRaises(Invalid):
            self.check()
    def test_disabled_section_reserves_nothing(self):
        self.env['ai']['enabled'] = False
        self.env['apps']['bot']['variables']['AI__API_KEY'] = 'OTHER'
        self.check()
    def test_key_is_generated_not_read_from_provider(self):
        # litellm_key.key write-only: из провайдера всегда null, Secret остался бы без AI_API_KEY.
        tf = (ROOT / 'modules/ai/main.tf').read_text(encoding='utf-8')
        self.assertNotIn('litellm_key.issued.key', tf)
        self.assertNotRegex(tf, r'litellm_key\.\w+\.key')
        self.assertIn('random_password', tf)
        self.assertIn('API_KEY"  = local.api_key', tf)
        self.assertRegex(tf, r'(?m)^\s+key\s+= local\.api_key$')
    def test_postgres_pooler_flag(self):
        self.env['postgres']['pooler'] = False
        self.check()
        self.env['postgres']['pooler'] = 'no'
        with self.assertRaises(Invalid):
            self.check()

if __name__ == '__main__':
    unittest.main()
