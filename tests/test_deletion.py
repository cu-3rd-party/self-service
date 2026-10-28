import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import yaml
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import load, validate, validate_project
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup_tls', ROOT / 'scripts/cleanup-tls.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)

class DeletionConfiguration(unittest.TestCase):
    def test_resources_without_apps_and_empty_environments(self):
        p = load(ROOT / 'examples/telegram-bot.yaml')
        for value in [{}, None]:
            conf = copy.deepcopy(p)
            if value is None:
                del conf['envs']['dev']['apps']
            else:
                conf['envs']['dev']['apps'] = value
            validate_project(conf, 'telegram-bot.yaml')
        p['envs'] = {}
        validate_project(p, 'telegram-bot.yaml')
    def test_delivery_does_not_recreate_deleted_project(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'deployments/removed/dev/backend.yaml'
            path.parent.mkdir(parents=True)
            path.write_text('repository: cu3rd/removed\ntag: old\nenv: {}\nsealedEnv: {}\n')
            self.assertEqual(validate(td), {})
    def test_only_one_resource_can_be_removed(self):
        p = load(ROOT / 'examples/telegram-bot.yaml')
        del p['envs']['dev']['postgres']
        validate_project(p, 'telegram-bot.yaml')
        self.assertTrue(p['envs']['dev']['s3']['enabled'])
        self.assertIn('bot', p['envs']['dev']['apps'])

class TLSCleanup(unittest.TestCase):
    def secret(self, name='route-tls', cert='route-cert'):
        return {'kind': 'Secret', 'type': 'kubernetes.io/tls', 'metadata': {'name': name, 'annotations': {'cert-manager.io/certificate-name': cert}}}
    def test_orphaned_certificate_secret_is_removed(self):
        self.assertEqual(cleanup.orphaned_tls([self.secret()]), ['route-tls'])
    def test_live_certificate_keeps_secret(self):
        self.assertEqual(cleanup.orphaned_tls([self.secret(), {'kind': 'Certificate', 'metadata': {'name': 'route-cert'}}]), [])
    def test_live_ingress_reference_keeps_secret(self):
        self.assertEqual(cleanup.orphaned_tls([self.secret(), {'kind': 'Ingress', 'spec': {'tls': [{'secretName': 'route-tls'}]}}]), [])
    def test_other_secrets_are_not_removed(self):
        user_tls = self.secret()
        user_tls['metadata']['annotations'] = {}
        opaque = self.secret()
        opaque['type'] = 'Opaque'
        self.assertEqual(cleanup.orphaned_tls([user_tls, opaque]), [])
