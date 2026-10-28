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

class IngressConfiguration(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.app = self.project['envs']['dev']['apps']['bot']
        self.app['ingress'] = [{'domain': 'testcontainer.dev.cu3rd.ru', 'targetPort': 8080}]
    def test_dev_and_prod_routes(self):
        self.project['envs']['prod'] = copy.deepcopy(self.project['envs']['dev'])
        self.project['envs']['prod']['apps']['bot']['ingress'][0]['domain'] = 'testcontainer.cu3rd.ru'
        validate_project(self.project, 'telegram-bot.yaml')
    def test_duplicate_domain_across_environments_rejected(self):
        self.project['envs']['prod'] = copy.deepcopy(self.project['envs']['dev'])
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'projects'
            folder.mkdir()
            (folder / 'telegram-bot.yaml').write_text(yaml.safe_dump(self.project))
            with self.assertRaises(Invalid):
                projects(td)
    def test_bad_domains_and_ports(self):
        for host in ['https://test.cu3rd.ru', 'test.cu3rd.ru:80', '*.cu3rd.ru', 'outside.example', '-bad.cu3rd.ru', 'git.cu3rd.ru', 'a' * 64 + '.cu3rd.ru']:
            self.app['ingress'][0]['domain'] = host
            with self.assertRaises(Invalid, msg=host):
                validate_project(self.project, 'telegram-bot.yaml')
        self.app['ingress'][0]['domain'] = 'valid.cu3rd.ru'
        for port in [True, '8080', 0, 65536]:
            self.app['ingress'][0]['targetPort'] = port
            with self.assertRaises(Invalid):
                validate_project(self.project, 'telegram-bot.yaml')
    def test_legacy_syntax_cannot_be_mixed(self):
        self.app['host'] = 'other.cu3rd.ru'
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_two_apps_can_share_domain_on_distinct_paths(self):
        self.app['ingress'][0]['paths'] = ['/api']
        other = copy.deepcopy(self.app)
        other['ingress'][0]['paths'] = ['/']
        self.project['envs']['dev']['apps']['frontend'] = other
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'projects'
            folder.mkdir()
            path = folder / 'telegram-bot.yaml'
            path.write_text(yaml.safe_dump(self.project))
            projects(td)
            other['ingress'][0]['paths'] = ['/api']
            path.write_text(yaml.safe_dump(self.project))
            with self.assertRaises(Invalid):
                projects(td)

@unittest.skipUnless(shutil.which('helm'), 'Helm render tests require helm')
class RenderIngress(unittest.TestCase):
    def test_ports_tls_and_multiple_domains(self):
        routes = [
            {'domain': 'testcontainer.dev.cu3rd.ru', 'targetPort': 8080},
            {'domain': 'admin.dev.cu3rd.ru', 'targetPort': 9090, 'paths': ['/api', '/health']},
            {'domain': 'alias.dev.cu3rd.ru', 'targetPort': 8080},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
            yaml.safe_dump({'routes': routes, 'port': 8080}, f)
            f.flush()
            text = subprocess.check_output(['helm', 'template', 'sample-dev-api', str(ROOT / 'charts/app'), '--namespace', 'cu3rd-sample-dev', '-f', f.name], text=True)
        manifests = [d for d in yaml.safe_load_all(text) if d]
        services = {d['metadata']['name']: d for d in manifests if d['kind'] == 'Service'}
        self.assertEqual(services['sample-dev-api-p8080']['spec']['ports'], [{'name': 'http', 'port': 80, 'targetPort': 8080}])
        self.assertEqual(services['sample-dev-api-p9090']['spec']['ports'][0]['targetPort'], 9090)
        ingress = next(d for d in manifests if d['kind'] == 'Ingress')
        self.assertEqual(ingress['spec']['ingressClassName'], 'traefik')
        self.assertEqual(ingress['metadata']['annotations']['cert-manager.io/cluster-issuer'], 'letsencrypt')
        self.assertEqual(set(ingress['spec']['tls'][0]['hosts']), {r['domain'] for r in routes})
        rules = {r['host']: r['http']['paths'] for r in ingress['spec']['rules']}
        self.assertEqual([p['path'] for p in rules['admin.dev.cu3rd.ru']], ['/api', '/health'])
        self.assertEqual(rules['admin.dev.cu3rd.ru'][0]['backend']['service'], {'name': 'sample-dev-api-p9090', 'port': {'number': 80}})
        self.assertEqual(rules['testcontainer.dev.cu3rd.ru'][0]['path'], '/')
        self.assertTrue(any(d['kind'] == 'Middleware' and d['spec']['redirectScheme']['scheme'] == 'https' for d in manifests))
