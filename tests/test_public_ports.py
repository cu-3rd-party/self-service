from pathlib import Path
import sys
import tempfile
import unittest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, projects, validate_project
ROOT = Path(__file__).resolve().parents[1]

class PublicPorts(unittest.TestCase):
    def setUp(self):
        self.project = load(ROOT / 'examples/telegram-bot.yaml')
        self.app = self.project['envs']['dev']['apps']['bot']
        self.app['port'] = 8080
        self.app['publicPorts'] = [{'name': 'rtc-udp', 'port': 31882, 'protocol': 'UDP'}]
    def rejected(self):
        with self.assertRaises(Invalid):
            validate_project(self.project, 'telegram-bot.yaml')
    def test_valid_port(self):
        validate_project(self.project, 'telegram-bot.yaml')
    def test_same_number_on_both_protocols(self):
        self.app['publicPorts'].append({'name': 'rtc-tcp', 'port': 31882, 'protocol': 'TCP'})
        validate_project(self.project, 'telegram-bot.yaml')
    def test_port_outside_nodeport_range(self):
        for port in [443, 29999, 32768, '31882']:
            self.app['publicPorts'][0]['port'] = port
            self.rejected()
    def test_bad_protocol_and_name(self):
        self.app['publicPorts'][0]['protocol'] = 'SCTP'
        self.rejected()
        self.app['publicPorts'][0]['protocol'] = 'UDP'
        for name in ['http', 'metrics', 'A', 'way-too-long-port-name']:
            self.app['publicPorts'][0]['name'] = name
            self.rejected()
    def test_duplicates_in_application(self):
        self.app['publicPorts'].append({'name': 'other', 'port': 31882, 'protocol': 'UDP'})
        self.rejected()
    def test_requires_application_port(self):
        self.app['port'] = None
        self.rejected()
    def test_port_claimed_once_across_projects(self):
        other = yaml.safe_load(yaml.safe_dump(self.project))
        other['name'] = 'other-bot'
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / 'projects'
            folder.mkdir()
            (folder / 'telegram-bot.yaml').write_text(yaml.safe_dump(self.project))
            (folder / 'other-bot.yaml').write_text(yaml.safe_dump(other))
            with self.assertRaises(Invalid):
                projects(td)
    def test_chart_and_module_wire_public_ports(self):
        service = (ROOT / 'charts/app/templates/public-service.yaml').read_text()
        self.assertIn('type: NodePort', service)
        self.assertIn('externalTrafficPolicy: Local', service)
        module = (ROOT / 'modules/project/main.tf').read_text()
        self.assertIn('publicPorts = try(each.value.publicPorts, [])', module)
