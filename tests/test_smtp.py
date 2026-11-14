from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, validate_project
ROOT = Path(__file__).resolve().parents[1]

class SmtpTests(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.env = self.project['envs']['dev']
        self.variables = self.env['apps']['bot'].setdefault('variables', {})
    def check(self):
        validate_project(self.project, 'telegram-bot.yaml')
    def test_valid_sections(self):
        for smtp in [{'enabled': True}, {'enabled': True, 'targetEnvPrefix': 'MAIL__'}, {'enabled': False}, {'enabled': True, 'targetEnvPrefix': ''}]:
            with self.subTest(smtp):
                self.env['smtp'] = smtp
                self.check()
    def test_invalid_sections(self):
        for smtp in [{'enabled': 'yes'}, {'enabled': True, 'host': 'smtp.gmail.com'}, {'enabled': True, 'targetEnvPrefix': 'smtp-'}, {'enabled': True, 'targetEnvPrefix': 5}]:
            with self.subTest(smtp):
                self.env['smtp'] = smtp
                with self.assertRaises(Invalid):
                    self.check()
    def test_platform_credentials_cannot_be_overridden(self):
        for prefix, name in [('SMTP_', 'SMTP_PASSWORD'), ('SMTP_', 'SMTP_HOST'), ('MAIL__', 'MAIL__USER')]:
            with self.subTest(name):
                self.setUp()
                self.env['smtp'] = {'enabled': True, 'targetEnvPrefix': prefix}
                self.variables[name] = 'OTHER'
                with self.assertRaises(Invalid):
                    self.check()
    def test_disabled_section_reserves_nothing(self):
        self.env['smtp'] = {'enabled': False}
        self.variables['SMTP_PASSWORD'] = 'OTHER'
        self.check()
    def test_library_uses_platform_mailbox(self):
        project = load(ROOT / 'projects/library.yaml')
        validate_project(project, 'library.yaml')
        for env in project['envs'].values():
            self.assertTrue(env['smtp']['enabled'])
    def test_secret_holds_all_settings(self):
        tf = (ROOT / 'modules/smtp/main.tf').read_text(encoding='utf-8')
        for key in ['HOST', 'PORT', 'USER', 'PASSWORD']:
            self.assertIn(f'targetEnvPrefix}}{key}"', tf)
        self.assertIn('-smtp"] : []', (ROOT / 'modules/project/main.tf').read_text(encoding='utf-8'))

if __name__ == '__main__':
    unittest.main()
