import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, projects, validate_project
ROOT = Path(__file__).resolve().parents[1]
KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPOWcaWv0dW4gz7c6HHvLvox69QhCzUg9O9LuWjnRVTY someone@laptop'
OTHER = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBWdHY2ldNqM7XNhvBzhKg0aOpoiF7D8na6JJTUns0qA'

class SshConfiguration(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.app = self.project['envs']['dev']['apps']['bot']
        self.app['ssh'] = {'user': 'vm', 'authorizedKeys': [KEY]}
    def reject(self):
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_minimal_block_accepted(self):
        validate_project(self.project, 'telegram-bot.yaml')
    def test_login_port_and_several_keys_accepted(self):
        self.app['ssh'].update(login='my-vm', port=2022, authorizedKeys=[KEY, OTHER])
        validate_project(self.project, 'telegram-bot.yaml')
    def test_root_rejected(self):
        self.app['ssh']['user'] = 'root'
        self.reject()
    def test_keys_required(self):
        self.app['ssh']['authorizedKeys'] = []
        self.reject()
    def test_key_options_rejected(self):
        self.app['ssh']['authorizedKeys'] = ['command="sh" ' + KEY]
        self.reject()
    def test_multiline_key_rejected(self):
        self.app['ssh']['authorizedKeys'] = [KEY + '\n' + OTHER]
        self.reject()
    def test_private_key_rejected(self):
        self.app['ssh']['authorizedKeys'] = ['-----BEGIN OPENSSH PRIVATE KEY-----']
        self.reject()
    def test_duplicate_key_rejected(self):
        self.app['ssh']['authorizedKeys'] = [KEY, KEY.rsplit(' ', 1)[0] + ' other-comment']
        self.reject()
    def test_privileged_port_rejected(self):
        self.app['ssh']['port'] = 22
        self.reject()
    def test_port_shared_with_http_rejected(self):
        self.app['port'] = 2222
        self.reject()
    def test_bad_login_rejected(self):
        self.app['ssh']['login'] = 'Root@host'
        self.reject()
    def test_unknown_key_rejected(self):
        self.app['ssh']['password'] = 'x'
        self.reject()
    def test_ssh_extra_port_name_reserved(self):
        self.app.setdefault('values', {})['extraPorts'] = {'ssh': 2022}
        self.reject()
    def test_login_claimed_twice_rejected(self):
        self.app['ssh']['login'] = 'shared'
        other = copy.deepcopy(self.project)
        other['name'] = 'other-bot'
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'projects'
            folder.mkdir()
            (folder / 'telegram-bot.yaml').write_text(yaml.safe_dump(self.project))
            (folder / 'other-bot.yaml').write_text(yaml.safe_dump(other))
            with self.assertRaises(Invalid):
                projects(Path(td))

@unittest.skipUnless(shutil.which('helm'), 'helm is not installed')
class SshChart(unittest.TestCase):
    def render(self, *sets):
        out = subprocess.run(['helm', 'template', 'demo', str(ROOT / 'charts/app'), '--set', 'image.repository=x,image.tag=y', *sets], check=True, capture_output=True, text=True).stdout
        return {(d['kind'], d['metadata']['name']): d for d in yaml.safe_load_all(out) if d}
    def test_disabled_by_default(self):
        docs = self.render()
        self.assertNotIn(('Service', 'demo-ssh'), docs)
        self.assertNotIn(('ConfigMap', 'demo-ssh'), docs)
    def test_gateway_key_service_and_port(self):
        docs = self.render('--set', 'port=null,ssh.enabled=true,ssh.port=2022', '--set-string', 'ssh.authorizedKeys=' + KEY)
        self.assertEqual(docs[('ConfigMap', 'demo-ssh')]['data']['authorized_keys'], KEY + '\n')
        self.assertEqual(docs[('Service', 'demo-ssh')]['spec']['ports'], [{'name': 'ssh', 'port': 2022, 'targetPort': 'ssh'}])
        self.assertNotIn(('Service', 'demo'), docs)
        pod = docs[('Deployment', 'demo')]['spec']['template']['spec']
        container = pod['containers'][0]
        self.assertEqual(container['ports'], [{'name': 'ssh', 'containerPort': 2022}])
        self.assertEqual(container['volumeMounts'], [{'name': 'ssh', 'mountPath': '/run/self-service/ssh', 'readOnly': True}])
        self.assertEqual(pod['volumes'], [{'name': 'ssh', 'configMap': {'name': 'demo-ssh'}}])
    def test_http_port_kept_next_to_ssh(self):
        docs = self.render('--set', 'ssh.enabled=true')
        names = [p['name'] for p in docs[('Deployment', 'demo')]['spec']['template']['spec']['containers'][0]['ports']]
        self.assertEqual(names, ['http', 'ssh'])

if __name__ == '__main__':
    unittest.main()
