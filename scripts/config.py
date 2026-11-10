"""Strict project/delivery validation shared by CI and deploy tooling."""
import re
import sys
from pathlib import Path
import yaml

NAME = re.compile(r"^[a-z][a-z0-9-]{1,24}[a-z0-9]$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SOURCE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
MODEL = re.compile(r"^[a-z0-9][a-z0-9_.-]*/[A-Za-z0-9_.:-]+$")
SSH_LOGIN = re.compile(r"^[a-z][a-z0-9-]{1,61}[a-z0-9]$")
SSH_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
# One public key per entry, no authorized_keys options: the gateway decides who gets in.
SSH_KEY = re.compile(r"^(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com) [A-Za-z0-9+/]{32,}={0,2}(?: [ -~]{1,100})?$")
# Зоны с /dev/kvm, где стоит KubeVirt (homelab kubevirt/), и образы charts/vm/values.yaml.
KVM_ZONES = {"nxs"}
VM_OS = {"alpine-3.24"}
ALLOWED_VALUES = {"replicas", "strategy", "resources", "probes", "persistence", "emptyDirs", "configFiles", "imagePullSecrets", "sealedPullSecret", "extraPorts"}
class Invalid(ValueError):
    pass
class UniqueLoader(yaml.SafeLoader):
    pass
def mapping(loader, node, deep=False):
    result = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if not isinstance(key, str) or key in result:
            raise Invalid("YAML keys must be unique strings")
        result[key] = loader.construct_object(v, deep=deep)
    return result
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
def load(path):
    try:
        return yaml.load(Path(path).read_text(), Loader=UniqueLoader)
    except yaml.YAMLError:
        raise Invalid(f"Invalid YAML: {path}") from None

def keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise Invalid(f"Expected keys {sorted(allowed)}; required {list(required)}")
def named(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise Invalid("Names: 3–26 lowercase letters/digits/hyphens, beginning with a letter")
def mappings(obj):
    if not isinstance(obj, dict) or any(not ENV.fullmatch(k) or not isinstance(v, str) or not SOURCE.fullmatch(v) for k, v in obj.items()):
        raise Invalid("Mappings must be ENV_NAME: ACTIONS_NAME (uppercase Actions names)")
def quantity(value, unit):
    m = re.fullmatch(r"([1-9][0-9]*)(Mi|Gi)", str(value))
    if not m:
        raise Invalid("Memory/storage must use Mi or Gi")
    return int(m[1]) * (1024 if m[2] == "Gi" else 1)

def ingress_routes(app):
    """Normalize the legacy host syntax for global ownership checks."""
    if 'ingress' in app:
        return app['ingress']
    if app.get('host'):
        return [{'domain': app['host'], 'targetPort': app.get('port'), 'paths': app.get('paths', ['/'])}]
    return []

def domain(value):
    if not isinstance(value, str) or len(value) > 253 or not value.endswith('.cu3rd.ru'):
        raise Invalid('Ingress domain must be below cu3rd.ru')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in value.split('.')):
        raise Invalid('Invalid ingress domain: use lowercase DNS labels, no schemes, wildcards or ports')
    if value in {'git.cu3rd.ru', 'vault.cu3rd.ru', 'argocd.cu3rd.ru', 'grafana.cu3rd.ru'}:
        raise Invalid('Ingress domain is reserved for platform services')

def ssh_login(project, env, name, app):
    """Name a person passes to the gateway: ssh -p 8222 <login>@ssh.cu3rd.ru."""
    return app['ssh'].get('login', f"{project}-{env}-{name}")

def ssh_access(ssh):
    keys(ssh, {'user', 'port', 'login', 'authorizedKeys'}, {'user', 'authorizedKeys'})
    if not isinstance(ssh['user'], str) or not SSH_USER.fullmatch(ssh['user']) or ssh['user'] == 'root':
        raise Invalid('ssh.user: the non-root user sshd in the container accepts')
    if type(ssh.get('port', 2222)) is not int or not 1024 <= ssh.get('port', 2222) <= 65535:
        raise Invalid('ssh.port must be 1024–65535')
    if 'login' in ssh and (not isinstance(ssh['login'], str) or not SSH_LOGIN.fullmatch(ssh['login'])):
        raise Invalid('ssh.login: 3–63 lowercase letters/digits/hyphens, beginning with a letter')
    listed = ssh['authorizedKeys']
    if not isinstance(listed, list) or not 1 <= len(listed) <= 50 or any(not isinstance(k, str) or not SSH_KEY.fullmatch(k) for k in listed):
        raise Invalid('ssh.authorizedKeys: 1–50 public keys, each "<type> <base64> [comment]" without options')
    if len({k.split()[1] for k in listed}) != len(listed):
        raise Invalid('Duplicate ssh.authorizedKeys')

def route_paths(paths):
    if not isinstance(paths, list) or not paths or any(not isinstance(x, str) or not x.startswith('/') for x in paths):
        raise Invalid('paths must start with /')
    if len(set(paths)) != len(paths):
        raise Invalid('Duplicate ingress paths')

def validate_project(p, filename):
    keys(p, {"name", "team", "envs"}, {"name", "team", "envs"})
    named(p["name"])
    if p["name"] != Path(filename).stem:
        raise Invalid("Project name must equal filename")
    named(p["team"])
    if not isinstance(p["envs"], dict):
        raise Invalid("envs must be a mapping")
    for env, e in p["envs"].items():
        if env not in {"dev", "prod", "test", "staging"}:
            raise Invalid("Environment: dev/prod/test/staging")
        keys(e, {"zone", "quota", "postgres", "s3", "ai", "apps", "vms"})
        if e.get("zone", "nxs") not in {"nxs", "grm", "xmsk", "xgrm"}:
            raise Invalid("Unknown zone")
        q = e.get("quota", {})
        keys(q, {"cpu", "memory", "storage"})
        if not 0 < float(q.get("cpu", 2)) <= 4 or quantity(q.get("memory", "4Gi"), "memory") > 8192 or quantity(q.get("storage", "5Gi"), "storage") > 20480:
            raise Invalid("Quota limit: 4 CPU, 8Gi memory, 20Gi storage")
        reserved = set()
        db = e.get("postgres", {})
        keys(db, {"enabled", "targetEnv", "format", "pooler"})
        if not isinstance(db.get("enabled", False), bool) or db.get("format", "url") not in {"url", "npgsql"} or not isinstance(db.get("pooler", True), bool):
            raise Invalid("Invalid postgres configuration")
        if not ENV.fullmatch(db.get("targetEnv", "DATABASE_URL")):
            raise Invalid("Invalid postgres targetEnv")
        if db.get("enabled"):
            reserved.add(db.get("targetEnv", "DATABASE_URL"))
        s3 = e.get("s3", {})
        keys(s3, {"enabled", "targetEnvPrefix", "quotaBytes"})
        if not isinstance(s3.get("enabled", False), bool) or not isinstance(s3.get("quotaBytes", 2147483648), int) or not 0 < s3.get("quotaBytes", 2147483648) <= 21474836480:
            raise Invalid("S3 quotaBytes: positive integer up to 20Gi")
        prefix = s3.get("targetEnvPrefix", "S3_")
        if not isinstance(prefix, str) or (prefix and not ENV.fullmatch(prefix)):
            raise Invalid("Invalid S3 prefix")
        if s3.get("enabled"):
            reserved |= {prefix + x for x in ["ACCESS_KEY", "SECRET_KEY", "URL", "BUCKET_NAME"]}
        ai = e.get("ai", {})
        keys(ai, {"enabled", "targetEnvPrefix", "model", "models", "budgetUsd", "budgetPeriod", "rpm", "tpm"})
        if not isinstance(ai.get("enabled", False), bool):
            raise Invalid("ai.enabled must be boolean")
        models = ai.get("models", [])
        if not isinstance(models, list) or any(not isinstance(m, str) or not MODEL.fullmatch(m) for m in models) or len(set(models)) != len(models):
            raise Invalid("ai.models: unique OpenRouter model ids, e.g. openai/gpt-4o-mini")
        if "model" in ai and (not isinstance(ai["model"], str) or not MODEL.fullmatch(ai["model"]) or (models and ai["model"] not in models)):
            raise Invalid("ai.model must be an OpenRouter model id listed in ai.models")
        budget = ai.get("budgetUsd")
        if budget is not None and (type(budget) not in {int, float} or not budget > 0):
            raise Invalid("ai.budgetUsd must be a positive number")
        if "budgetPeriod" in ai and (budget is None or not isinstance(ai["budgetPeriod"], str) or not re.fullmatch(r"[1-9][0-9]{0,2}[hd]", ai["budgetPeriod"])):
            raise Invalid("ai.budgetPeriod (e.g. 1d, 7d, 30d) requires ai.budgetUsd")
        if any(k in ai and (type(ai[k]) is not int or ai[k] <= 0) for k in ("rpm", "tpm")):
            raise Invalid("ai.rpm/ai.tpm must be positive integers")
        prefix = ai.get("targetEnvPrefix", "AI_")
        if not isinstance(prefix, str) or (prefix and not ENV.fullmatch(prefix)):
            raise Invalid("Invalid ai prefix")
        if ai.get("enabled"):
            reserved |= {prefix + x for x in ["API_KEY", "BASE_URL", "MODEL"]}
        if not isinstance(e.get("apps", {}), dict):
            raise Invalid("apps must be a mapping")
        for name, app in e.get("apps", {}).items():
            named(name)
            if len(p['name'] + '-' + env + '-' + name) > 53:
                raise Invalid("Combined release name exceeds 53 characters")
            keys(app, {"repo", "image", "tag", "port", "host", "paths", "ingress", "metrics", "ssh", "secrets", "variables", "values"}, {"repo", "image", "tag"})
            if not isinstance(app["repo"], str) or not re.fullmatch(r"cu3rd/[A-Za-z0-9_.-]+", app["repo"]):
                raise Invalid("repo must belong to cu3rd")
            if not isinstance(app["image"], str) or not re.fullmatch(r"git\.cu3rd\.ru/cu3rd(?:-private)?/[a-z0-9_.-]+", app["image"]):
                raise Invalid("image must be in git.cu3rd.ru/cu3rd or git.cu3rd.ru/cu3rd-private")
            if not isinstance(app["tag"], str) or not TAG.fullmatch(app["tag"]):
                raise Invalid("Invalid image tag")
            port = app.get("port")
            if port is not None and (type(port) is not int or not 1024 <= port <= 65535):
                raise Invalid("port must be null or 1024–65535")
            if 'ingress' in app and ('host' in app or 'paths' in app):
                raise Invalid('Use ingress or legacy host/paths, not both')
            if 'ingress' in app and not isinstance(app['ingress'], list):
                raise Invalid('ingress must be a list')
            seen = set()
            for route in ingress_routes(app):
                keys(route, {'domain', 'targetPort', 'paths'}, {'domain', 'targetPort'})
                domain(route['domain'])
                if type(route['targetPort']) is not int or not 1024 <= route['targetPort'] <= 65535:
                    raise Invalid('Ingress targetPort must be 1024–65535')
                route_paths(route.get('paths', ['/']))
                if route['domain'] in seen:
                    raise Invalid('Declare each domain once per application; combine paths in one entry')
                seen.add(route['domain'])
            route_paths(app.get('paths', ['/']))
            metrics = app.get('metrics', {})
            keys(metrics, {'enabled', 'port', 'path', 'interval'})
            if type(metrics.get('enabled', False)) is not bool:
                raise Invalid('metrics.enabled must be boolean')
            if 'port' in metrics and (type(metrics['port']) is not int or not 1024 <= metrics['port'] <= 65535):
                raise Invalid('metrics.port must be 1024–65535')
            if not isinstance(metrics.get('path', '/metrics'), str) or not metrics.get('path', '/metrics').startswith('/'):
                raise Invalid('metrics.path must start with /')
            if metrics.get('interval', '30s') not in {'15s', '30s', '60s'}:
                raise Invalid('metrics.interval must be 15s, 30s or 60s')
            if metrics.get('enabled') and 'metrics' in app.get('values', {}).get('extraPorts', {}):
                raise Invalid('Port name metrics is reserved when metrics are enabled')
            if 'ssh' in app:
                ssh_access(app['ssh'])
                if 'ssh' in app.get('values', {}).get('extraPorts', {}):
                    raise Invalid('Port name ssh is reserved when ssh is declared')
                if app['ssh'].get('port', 2222) in {app.get('port'), metrics.get('port') if metrics.get('enabled') else None, *[r['targetPort'] for r in ingress_routes(app)], *app.get('values', {}).get('extraPorts', {}).values()}:
                    raise Invalid('ssh.port must differ from the other ports of the application')
            secrets, variables = app.get("secrets", {}), app.get("variables", {})
            mappings(secrets)
            mappings(variables)
            if set(secrets) & set(variables) or (set(secrets) | set(variables)) & reserved:
                raise Invalid("Environment names overlap secrets/variables/generated credentials")
            keys(app.get("values", {}), ALLOWED_VALUES)
        vms = e.get("vms", {})
        if not isinstance(vms, dict):
            raise Invalid("vms must be a mapping")
        if vms and e.get("zone", "nxs") not in KVM_ZONES:
            raise Invalid(f"vms need a zone with hardware virtualization: {', '.join(sorted(KVM_ZONES))}")
        for name, vm in vms.items():
            validate_vm(p["name"], env, name, vm)
            if name in e.get("apps", {}):
                raise Invalid("A VM and an application cannot share a name")
    return p

def validate_vm(project, env, name, vm):
    named(name)
    if len(project + '-' + env + '-' + name) > 53:
        raise Invalid("Combined release name exceeds 53 characters")
    keys(vm, {"os", "cpu", "memory", "disk", "ssh"})
    if vm.get("os", "alpine-3.24") not in VM_OS:
        raise Invalid(f"vm os: one of {', '.join(sorted(VM_OS))}")
    if type(vm.get("cpu", 1)) is not int or not 1 <= vm.get("cpu", 1) <= 4:
        raise Invalid("vm cpu: whole cores 1–4")
    if not 128 <= quantity(vm.get("memory", "512Mi"), "memory") <= 4096:
        raise Invalid("vm memory: 128Mi–4Gi")
    if not 1024 <= quantity(vm.get("disk", "2Gi"), "storage") <= 20480:
        raise Invalid("vm disk: 1Gi–20Gi")
    if "ssh" in vm:
        if "port" in vm["ssh"]:
            raise Invalid("vm ssh listens on 22; ssh.port is for containers")
        ssh_access(vm["ssh"])

def projects(root):
    result = {}
    hosts = {}
    routes = set()
    logins = set()
    for path in sorted((Path(root) / "projects").glob("*.yaml")):
        p = validate_project(load(path), path)
        result[p["name"]] = p
        for env, e in p['envs'].items():
            for name, vm in e.get('vms', {}).items():
                if 'ssh' in vm:
                    login = ssh_login(p['name'], env, name, vm)
                    if login in logins:
                        raise Invalid('SSH login is already claimed by another application')
                    logins.add(login)
            for name, a in e.get('apps', {}).items():
                if 'ssh' in a:
                    login = ssh_login(p['name'], env, name, a)
                    if login in logins:
                        raise Invalid('SSH login is already claimed by another application')
                    logins.add(login)
                for route in ingress_routes(a):
                    h = route['domain']
                    owner = (p['name'], env)
                    if h in hosts and hosts[h] != owner:
                        raise Invalid('Host is already claimed by another project/environment')
                    hosts[h] = owner
                    for path in route.get('paths', ['/']):
                        key = (h, path)
                        if key in routes:
                            raise Invalid('Domain/path is already routed by another application')
                        routes.add(key)
    return result

def validate_delivery(d, app, pending_ok=False):
    """Return True when a stored delivery predates newly declared mappings."""
    keys(d, {"repository", "tag", "env", "sealedEnv"}, {"repository", "tag", "env", "sealedEnv"})
    if d["repository"] != app["repo"] or not isinstance(d["tag"], str) or not TAG.fullmatch(d["tag"]):
        raise Invalid("Delivery repository/tag mismatch")
    pending = False
    for field, mapping_name in [("env", "variables"), ("sealedEnv", "secrets")]:
        declared = set(app.get(mapping_name, {}))
        if not isinstance(d[field], dict) or not set(d[field]) <= declared:
            raise Invalid(f"Delivery {field} must match declared {mapping_name} exactly")
        if set(d[field]) != declared:
            # Mappings added after the last delivery: keep it until CI redelivers.
            if not pending_ok:
                raise Invalid(f"Delivery {field} must match declared {mapping_name} exactly")
            pending = True
        if any(not isinstance(v, str) for v in d[field].values()):
            raise Invalid("Delivery values must be strings")
    for value in d['sealedEnv'].values():
        if len(value) < 200 or not re.fullmatch(r"[A-Za-z0-9+/]+=*", value):
            raise Invalid("Expected kubeseal ciphertext, never plaintext")
    return pending

def validate(root):
    ps = projects(root)
    for path in (Path(root) / 'deployments').rglob('*.yaml'):
        rel = path.relative_to(Path(root) / 'deployments').parts
        if len(rel) != 3:
            raise Invalid("Delivery path: deployments/project/env/app.yaml")
        project, env, app = rel[0], rel[1], Path(rel[2]).stem
        try:
            conf = ps[project]['envs'][env]['apps'][app]
        except KeyError:
            # Deliveries do not declare resources. Ignore inactive app snapshots.
            continue
        if validate_delivery(load(path), conf, pending_ok=True):
            print(f"Delivery {project}/{env}/{app} is pending redelivery", file=sys.stderr)
    return ps
