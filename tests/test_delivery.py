import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, validate_project, validate_delivery, projects
from deploy import payload, select
ROOT = Path(__file__).resolve().parents[1]

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.app = self.project['envs']['dev']['apps']['bot']
    def test_example(self):
        validate_project(self.project, 'telegram-bot.yaml')
    def test_only_mapped_values_and_correct_sealing_scope(self):
        cipher = 'Ag' + 'A' * 700
        with patch('deploy.subprocess.run', return_value=subprocess.CompletedProcess([], 0, cipher.encode(), b'')) as run:
            d = payload(self.app, 'cu3rd-telegram-bot-dev', 'telegram-bot-dev-bot', 'abc123',
                {'TELEGRAM_BOT_TOKEN': 'private', 'REGISTRY_TOKEN': 'do-not-deliver'},
                {'TELEGRAM_BOT_NAME': 'sample_bot', 'EXTRA': 'ignored'}, 'cert.pem')
        self.assertEqual(d['env'], {'TELEGRAM_BOT_NAME': 'sample_bot'})
        self.assertEqual(d['sealedEnv'], {'TELEGRAM_BOT_TOKEN': cipher})
        self.assertNotIn('private', json.dumps(d))
        self.assertNotIn('do-not-deliver', json.dumps(d))
        args, kwargs = run.call_args
        self.assertIn('cu3rd-telegram-bot-dev', args[0])
        self.assertIn('telegram-bot-dev-bot-env', args[0])
        self.assertIn('strict', args[0])
        self.assertEqual(kwargs['input'], b'private')
    def test_missing_secret_fails(self):
        with self.assertRaises(Invalid):
            select(self.app['secrets'], {})
    def test_empty_variable_fails(self):
        with self.assertRaises(Invalid):
            select(self.app['variables'], {'TELEGRAM_BOT_NAME': ''})
    def test_multiline_and_shell_metacharacters_remain_data(self):
        value = 'line1\n$(touch /tmp/should-not-exist)\n`id`'
        self.assertEqual(select({'TOKEN': 'TOKEN'}, {'TOKEN': value})['TOKEN'], value)
    def test_generated_credentials_cannot_be_overridden(self):
        self.app['variables']['DB_CONNSTRING'] = 'OTHER'
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_secret_variable_collision(self):
        self.app['variables']['TELEGRAM_BOT_TOKEN'] = 'OTHER'
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_plaintext_and_extra_delivery_fields_rejected(self):
        d = {'repository': self.app['repo'], 'tag': 'abc', 'env': {'TELEGRAM_BOT_NAME': 'bot'}, 'sealedEnv': {'TELEGRAM_BOT_TOKEN': 'plaintext'}}
        with self.assertRaises(Invalid):
            validate_delivery(d, self.app)
        d['sealedEnv']['TELEGRAM_BOT_TOKEN'] = 'Ag' + 'A' * 700
        d['env']['REGISTRY_TOKEN'] = 'oops'
        with self.assertRaises(Invalid):
            validate_delivery(d, self.app)
    def test_delivery_missing_new_mappings_is_pending(self):
        d = {'repository': self.app['repo'], 'tag': 'abc', 'env': {}, 'sealedEnv': {}}
        with self.assertRaises(Invalid):
            validate_delivery(d, self.app)
        self.assertTrue(validate_delivery(d, self.app, pending_ok=True))
        d['env']['REGISTRY_TOKEN'] = 'oops'
        with self.assertRaises(Invalid):
            validate_delivery(d, self.app, pending_ok=True)
    def test_repository_mismatch(self):
        d = {'repository': 'cu3rd/other', 'tag': 'abc', 'env': {}, 'sealedEnv': {}}
        with self.assertRaises(Invalid):
            validate_delivery(d, self.app)
    def test_unknown_privileged_values_rejected(self):
        self.app['values'] = {'hostNetwork': True}
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_duplicate_yaml_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'duplicate.yaml'
            p.write_text('name: first\nname: second\n')
            with self.assertRaises(Invalid):
                load(p)
    def test_different_projects_cannot_claim_same_hostname(self):
        with tempfile.TemporaryDirectory() as t:
            import yaml
            p = Path(t) / 'projects'
            p.mkdir()
            for name in ['project-one', 'project-two']:
                conf = copy.deepcopy(self.project)
                conf['name'] = name
                conf['envs']['dev']['apps']['bot']['host'] = 'same.cu3rd.ru'
                (p / (name + '.yaml')).write_text(yaml.safe_dump(conf))
            with self.assertRaises(Invalid):
                projects(t)
    def test_plan_allows_remove_and_replace(self):
        for actions, code in [(['create'], 0), (['update'], 0), (['delete'], 0), (['delete', 'create'], 0)]:
            plan = {'resource_changes': [{'change': {'actions': actions}}]}
            p = subprocess.run([sys.executable, str(ROOT / 'scripts/check-plan.py')], input=json.dumps(plan), text=True, capture_output=True)
            self.assertEqual(p.returncode, code)

if __name__ == '__main__':
    unittest.main()
