#!/usr/bin/env python3
"""Collect cert-manager TLS secrets orphaned by deleted self-service ingresses.

The shared cert-manager installation does not enable certificate-owner-ref.
Only annotated TLS secrets in self-service namespaces are eligible.
"""
import json
import subprocess

def orphaned_tls(items):
    certificates = {x['metadata']['name'] for x in items if x['kind'] == 'Certificate'}
    referenced = {t['secretName'] for x in items if x['kind'] == 'Ingress' for t in x.get('spec', {}).get('tls', []) if t.get('secretName')}
    return [x['metadata']['name'] for x in items
            if x['kind'] == 'Secret' and x.get('type') == 'kubernetes.io/tls'
            and (name := x['metadata'].get('annotations', {}).get('cert-manager.io/certificate-name'))
            and name not in certificates and x['metadata']['name'] not in referenced]

def main():
    namespaces = json.loads(subprocess.check_output(['kubectl', 'get', 'namespaces', '-l', 'cu3rd.ru/project', '-o', 'json']))['items']
    for item in namespaces:
        ns = item['metadata']['name']
        if not ns.startswith('cu3rd-') or item['metadata'].get('deletionTimestamp'):
            continue
        objects = json.loads(subprocess.check_output(['kubectl', '-n', ns, 'get', 'certificates,ingresses,secrets', '-o', 'json']))['items']
        for name in orphaned_tls(objects):
            subprocess.run(['kubectl', '-n', ns, 'delete', 'secret', name, '--ignore-not-found', '--wait=false'], check=True)

if __name__ == '__main__':
    main()
