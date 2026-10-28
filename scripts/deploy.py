#!/usr/bin/env python3
"""Seal explicitly mapped Actions values and open a delivery PR. No cluster credentials."""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
import yaml
from config import Invalid, TAG, projects, validate_delivery

class API:
    def __init__(self, token):
        self.token = token
    def call(self, method, path, body=None):
        request = urllib.request.Request('https://git.cu3rd.ru/api/v1' + path,
            data=None if body is None else json.dumps(body).encode(), method=method,
            headers={'Authorization': 'token ' + self.token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as e:
            # API error bodies can echo submitted data. Do not print them.
            raise Invalid(f'Forgejo API returned HTTP {e.code}') from None

def select(mapping, available):
    normalized = {k.upper(): v for k, v in available.items()}
    result = {}
    for target, source in mapping.items():
        if source not in normalized or normalized[source] is None or normalized[source] == '':
            raise Invalid(f'Missing or empty Actions value: {source}')
        if not isinstance(normalized[source], str):
            raise Invalid('Actions values must be strings')
        result[target] = normalized[source]
    return result

def payload(app, namespace, release, tag, secrets, variables, cert, seal='kubeseal'):
    if not TAG.fullmatch(tag):
        raise Invalid('Invalid image tag')
    encrypted = {}
    for target, value in select(app.get('secrets', {}), secrets).items():
        r = subprocess.run([seal, '--raw', '--cert', str(cert), '--scope', 'strict',
            '--namespace', namespace, '--name', release + '-env', '--from-file=/dev/stdin'],
            input=value.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode:
            raise Invalid('kubeseal failed (output suppressed to protect secrets)')
        encrypted[target] = r.stdout.decode().strip()
    result = {'repository': app['repo'], 'tag': tag,
        'env': select(app.get('variables', {}), variables), 'sealedEnv': encrypted}
    validate_delivery(result, app)
    return result

def main():
    parser = argparse.ArgumentParser()
    for name in ['project', 'environment', 'app', 'tag']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    root = Path(args.root)
    ps = projects(root)
    try:
        app = ps[args.project]['envs'][args.environment]['apps'][args.app]
    except KeyError:
        raise Invalid('Unknown project/environment/application') from None
    if os.environ.get('SOURCE_REPOSITORY', '').lower() != app['repo'].lower():
        raise Invalid('Workflow repository must match the application repo')
    if os.environ.get('SOURCE_EVENT') not in {'push', 'workflow_dispatch'}:
        raise Invalid('Delivery is allowed only on push or workflow_dispatch, never PR events')
    if os.environ.get('SOURCE_REF') != 'refs/heads/' + os.environ.get('SOURCE_DEFAULT_BRANCH', 'master'):
        raise Invalid('Delivery must run from the source repository default branch')
    release = f'{args.project}-{args.environment}-{args.app}'
    ns = f'cu3rd-{args.project}-{args.environment}'
    data = payload(app, ns, release, args.tag,
        json.loads(os.environ.get('ACTIONS_SECRETS_JSON', '{}')),
        json.loads(os.environ.get('ACTIONS_VARIABLES_JSON', '{}')),
        root / 'certs/sealed-secrets.pem')
    api = API(os.environ['DELIVERY_TOKEN'])
    prefix = '/repos/cu3rd/self-service'
    default = api.call('GET', prefix + '/branches/master')['commit']['id']
    # The schema and certificate used to seal must be the current reviewed master.
    revision = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != default:
        raise Invalid('Self-service master changed; rerun delivery with the current master')
    branch = f'deploy/{args.project}/{args.environment}/{args.app}-{uuid.uuid4().hex[:10]}'
    api.call('POST', prefix + '/branches', {'new_branch_name': branch, 'old_ref_name': default})
    path = f'deployments/{args.project}/{args.environment}/{args.app}.yaml'
    content = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    body = {'branch': branch, 'message': f'deploy: {release} {args.tag}',
        'content': base64.b64encode(content.encode()).decode()}
    # Contents endpoint needs the existing blob SHA when replacing a file.
    try:
        old = api.call('GET', prefix + '/contents/' + path + '?ref=' + branch)
    except Invalid as e:
        if 'HTTP 404' not in str(e):
            raise
        old = None
    if old:
        body['sha'] = old['sha']
    api.call('PUT' if old else 'POST', prefix + '/contents/' + path, body)
    pr = api.call('POST', prefix + '/pulls', {'head': branch, 'base': 'master',
        'title': f'deploy: {release} {args.tag}',
        'body': f'Delivery from `{app["repo"]}`. Only declared variables and sealed secrets are included.\n\nReview and merge to deploy. Generated resource credentials are managed separately.'})
    print('Delivery PR: ' + pr['html_url'])

if __name__ == '__main__':
    try:
        main()
    except (Invalid, KeyError, ValueError, OSError) as e:
        # Never print exception payloads from JSON parsing: input may contain secrets.
        if isinstance(e, Invalid):
            print('Delivery rejected: ' + str(e), file=sys.stderr)
        else:
            print('Delivery failed: verify inputs, tooling and credentials', file=sys.stderr)
        sys.exit(1)
