import copy
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import config
from config import Invalid, load, validate_project
ROOT = Path(__file__).resolve().parents[1]
KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPOWcaWv0dW4gz7c6HHvLvox69QhCzUg9O9LuWjnRVTY someone@laptop'

class VmConfiguration(unittest.TestCase):
    def setUp(self):
        # KubeVirt выключен; проверяем блок vms так, будто он включён на nxs
        patcher = mock.patch.object(config, 'KVM_ZONES', {'nxs'})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.project = load(ROOT / 'tests/fixtures/alpine-kvm.yaml')
        self.env = self.project['envs']['prod']
        self.vm = self.env['vms']['box']
    def reject(self):
        with self.assertRaises(Invalid):
            validate_project(self.project, 'alpine-kvm.yaml')
    def test_example_accepted(self):
        validate_project(self.project, 'alpine-kvm.yaml')
    def test_defaults_accepted(self):
        self.env['vms']['box'] = {}
        validate_project(self.project, 'alpine-kvm.yaml')
    def test_rejected_while_kubevirt_off(self):
        with mock.patch.object(config, 'KVM_ZONES', set()):
            self.reject()
    def test_zone_without_kvm_rejected(self):
        self.env['zone'] = 'grm'
        self.reject()
    def test_unknown_os_rejected(self):
        self.vm['os'] = 'debian'
        self.reject()
    def test_limits(self):
        for field, value in [('cpu', 0), ('cpu', 8), ('cpu', '1'), ('memory', '64Mi'), ('memory', '8Gi'), ('disk', '512Mi'), ('disk', '40Gi')]:
            with self.subTest(field=field, value=value):
                saved = copy.deepcopy(self.vm)
                self.vm[field] = value
                self.reject()
                self.vm.clear(); self.vm.update(saved)
    def test_root_login_rejected(self):
        self.vm['ssh']['user'] = 'root'
        self.reject()
    def test_ssh_port_rejected(self):
        self.vm['ssh']['port'] = 2222
        self.reject()
    def test_name_shared_with_app_rejected(self):
        self.env['apps'] = {'box': {'repo': 'cu3rd/x', 'image': 'git.cu3rd.ru/cu3rd/x', 'tag': 'latest'}}
        self.reject()

class VmChart(unittest.TestCase):
    def render(self, **ssh):
        values = ['--set', 'nodeSelector.homelab/site=nxs', '--set', 'disk=4Gi', '--set', 'selfService.project=alpine-kvm']
        for k, v in ssh.items():
            values += ['--set', f'ssh.{k}={v}']
        text = subprocess.check_output(['helm', 'template', 'alpine-kvm-prod-box', str(ROOT / 'charts/vm'), *values], text=True)
        return [d for d in yaml.safe_load_all(text) if d]
    def test_vm_with_ssh(self):
        docs = self.render(enabled='true', user='vm', authorizedKeys=KEY)
        vm = next(d for d in docs if d['kind'] == 'VirtualMachine')
        self.assertEqual(vm['spec']['dataVolumeTemplates'][0]['spec']['storage']['resources']['requests']['storage'], '4Gi')
        spec = vm['spec']['template']['spec']
        self.assertEqual(spec['nodeSelector'], {'homelab/site': 'nxs'})
        cloud = yaml.safe_load(spec['volumes'][1]['cloudInitNoCloud']['userData'])
        self.assertEqual(cloud['users'][0]['ssh_authorized_keys'], [KEY])
        self.assertFalse(cloud['users'][0]['lock_passwd'])
        svc = next(d for d in docs if d['kind'] == 'Service')
        self.assertEqual(svc['metadata']['name'], 'alpine-kvm-prod-box-ssh')
        self.assertEqual(svc['spec']['selector'], {'vm.kubevirt.io/name': 'alpine-kvm-prod-box'})
    def test_vm_without_ssh_has_no_service(self):
        self.assertEqual([d['kind'] for d in self.render()], ['VirtualMachine'])
