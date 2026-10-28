"""Strict project/delivery validation shared by CI and deploy tooling."""
import re
from pathlib import Path
import yaml

NAME = re.compile(r"^[a-z][a-z0-9-]{1,24}[a-z0-9]$")
ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SOURCE = re.compile(r"^[A-Z_][A-Z0-9_]*$")
TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
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
    if not isinstance(p["envs"], dict) or not p["envs"]:
        raise Invalid("envs must be a nonempty mapping")
    for env, e in p["envs"].items():
        if env not in {"dev", "prod", "test", "staging"}:
            raise Invalid("Environment: dev/prod/test/staging")
        keys(e, {"zone", "quota", "postgres", "s3", "apps"}, {"apps"})
        if e.get("zone", "nxs") not in {"nxs", "grm"}:
            raise Invalid("Unknown zone")
        q = e.get("quota", {})
        keys(q, {"cpu", "memory", "storage"})
        if not 0 < float(q.get("cpu", 2)) <= 4 or quantity(q.get("memory", "4Gi"), "memory") > 8192 or quantity(q.get("storage", "5Gi"), "storage") > 20480:
            raise Invalid("Quota limit: 4 CPU, 8Gi memory, 20Gi storage")
        reserved = set()
        db = e.get("postgres", {})
        keys(db, {"enabled", "targetEnv", "format"})
        if not isinstance(db.get("enabled", False), bool) or db.get("format", "url") not in {"url", "npgsql"}:
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
        if not isinstance(e["apps"], dict) or not e["apps"]:
            raise Invalid("apps must be a nonempty mapping")
        for name, app in e["apps"].items():
            named(name)
            if len(p['name'] + '-' + env + '-' + name) > 53:
                raise Invalid("Combined release name exceeds 53 characters")
            keys(app, {"repo", "image", "tag", "port", "host", "paths", "ingress", "secrets", "variables", "values"}, {"repo", "image", "tag"})
            if not isinstance(app["repo"], str) or not re.fullmatch(r"cu3rd/[A-Za-z0-9_.-]+", app["repo"]):
                raise Invalid("repo must belong to cu3rd")
            if not isinstance(app["image"], str) or not re.fullmatch(r"git\.cu3rd\.ru/cu3rd/[a-z0-9_.-]+", app["image"]):
                raise Invalid("image must be in git.cu3rd.ru/cu3rd")
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
            secrets, variables = app.get("secrets", {}), app.get("variables", {})
            mappings(secrets)
            mappings(variables)
            if set(secrets) & set(variables) or (set(secrets) | set(variables)) & reserved:
                raise Invalid("Environment names overlap secrets/variables/generated credentials")
            keys(app.get("values", {}), ALLOWED_VALUES)
    return p

def projects(root):
    result = {}
    hosts = {}
    routes = set()
    for path in sorted((Path(root) / "projects").glob("*.yaml")):
        p = validate_project(load(path), path)
        result[p["name"]] = p
        for env, e in p['envs'].items():
            for a in e['apps'].values():
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

def validate_delivery(d, app):
    keys(d, {"repository", "tag", "env", "sealedEnv"}, {"repository", "tag", "env", "sealedEnv"})
    if d["repository"] != app["repo"] or not isinstance(d["tag"], str) or not TAG.fullmatch(d["tag"]):
        raise Invalid("Delivery repository/tag mismatch")
    for field, mapping_name in [("env", "variables"), ("sealedEnv", "secrets")]:
        if not isinstance(d[field], dict) or set(d[field]) != set(app.get(mapping_name, {})):
            raise Invalid(f"Delivery {field} must match declared {mapping_name} exactly")
        if any(not isinstance(v, str) for v in d[field].values()):
            raise Invalid("Delivery values must be strings")
    for value in d['sealedEnv'].values():
        if len(value) < 200 or not re.fullmatch(r"[A-Za-z0-9+/]+=*", value):
            raise Invalid("Expected kubeseal ciphertext, never plaintext")

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
            raise Invalid("Orphan delivery file") from None
        validate_delivery(load(path), conf)
    return ps
