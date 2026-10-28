from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from config import Invalid, load, validate_project
ROOT=Path(__file__).resolve().parents[1]
class MetricsConfig(unittest.TestCase):
    def test_worker_metrics(self):
        p=load(ROOT/'examples/telegram-bot.yaml')
        p['envs']['dev']['apps']['bot']['metrics']={'enabled':True,'port':9090}
        validate_project(p,'telegram-bot.yaml')
    def test_bad_metrics(self):
        for config in [{'enabled':'true'},{'port':80},{'port':True},{'path':'metrics'},{'interval':'1s'},{'token':'secret'}]:
            p=load(ROOT/'examples/telegram-bot.yaml')
            p['envs']['dev']['apps']['bot']['metrics']=config
            with self.assertRaises(Invalid):validate_project(p,'telegram-bot.yaml')

@unittest.skipUnless(shutil.which('helm'),'Helm required')
class MetricsChart(unittest.TestCase):
    def render(self,port,metrics):
        with tempfile.NamedTemporaryFile(mode='w',suffix='.yaml') as f:
            yaml.safe_dump({'port':port,'metrics':metrics,'selfService':{'project':'my-project','env':'dev','application':'worker'}},f);f.flush()
            text=subprocess.check_output(['helm','template','my-project-dev-worker',str(ROOT/'charts/app'),'-f',f.name],text=True)
        return [x for x in yaml.safe_load_all(text) if x]
    def test_disabled_keeps_infrastructure_labels_without_scrape(self):
        docs=self.render(None,{'enabled':False})
        self.assertFalse(any(x['kind']=='PodMonitor' for x in docs))
        d=next(x for x in docs if x['kind']=='Deployment')
        self.assertEqual(d['spec']['template']['metadata']['labels']['cu3rd.ru/project'],'my-project')
        self.assertEqual(d['spec']['selector']['matchLabels'],{'app.kubernetes.io/name':'my-project-dev-worker'})
        self.assertFalse(d['spec']['template']['spec']['automountServiceAccountToken'])
    def test_worker_with_separate_metrics_port(self):
        docs=self.render(None,{'enabled':True,'port':9090,'path':'/metrics','interval':'30s'})
        pm=next(x for x in docs if x['kind']=='PodMonitor')
        self.assertEqual(pm['spec']['podMetricsEndpoints'][0]['port'],'metrics')
        d=next(x for x in docs if x['kind']=='Deployment')
        self.assertEqual(d['spec']['template']['spec']['containers'][0]['ports'],[{'name':'metrics','containerPort':9090}])
        self.assertFalse(any(x['kind']=='Service' for x in docs))
    def test_metrics_on_http_port_and_custom_path(self):
        docs=self.render(8080,{'enabled':True,'port':8080,'path':'/internal/metrics','interval':'60s'})
        ep=next(x for x in docs if x['kind']=='PodMonitor')['spec']['podMetricsEndpoints'][0]
        self.assertEqual((ep['port'],ep['path'],ep['interval']),('http','/internal/metrics','60s'))
        ports=next(x for x in docs if x['kind']=='Deployment')['spec']['template']['spec']['containers'][0]['ports']
        self.assertEqual(ports,[{'name':'http','containerPort':8080}])
