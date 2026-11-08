#!/usr/bin/env python3
"""Install a pinned kubeseal release, checking its official SHA256SUMS.

If GitHub release downloads are unavailable (they return 504 during GitHub
outages), build the same version from the Go module proxy instead: a pinned
Go toolchain checked against its SHA256, the module checked by the Go checksum
database.
"""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request
version = '0.40.0'
name = f'kubeseal-{version}-linux-amd64.tar.gz'
base = f'https://github.com/bitnami-labs/sealed-secrets/releases/download/v{version}/'
go_version = '1.27.3'
go_sha256 = '65efbc80fdc1fa2cd2631cad5b481777a68e8725f34e89f50fc6ac714e379b40'
temp = Path(os.environ.get('RUNNER_TEMP', '/tmp'))
folder = temp / 'self-service-bin'
folder.mkdir(exist_ok=True)


def fetch(url, timeout, attempts=3):
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(url, timeout=timeout).read()
        except OSError as error:
            if attempt == attempts - 1:
                raise
            print(f'{url}: {error}, retrying')
            time.sleep(5 * (attempt + 1))


def from_release():
    blob = fetch(base + name, 60)
    sums = fetch(base + f'sealed-secrets_{version}_checksums.txt', 30).decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
    if hashlib.sha256(blob).hexdigest() != expected:
        raise SystemExit('kubeseal checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
        member = next(m for m in archive.getmembers() if m.name in {'kubeseal', './kubeseal'})
        binary = folder / 'kubeseal'
        binary.write_bytes(archive.extractfile(member).read())
        binary.chmod(0o755)


def from_go_proxy():
    blob = fetch(f'https://go.dev/dl/go{go_version}.linux-amd64.tar.gz', 300)
    if hashlib.sha256(blob).hexdigest() != go_sha256:
        raise SystemExit('go toolchain checksum mismatch')
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
        archive.extractall(temp, filter='data')
    env = {**os.environ, 'GOBIN': str(folder), 'GOTOOLCHAIN': 'local', 'CGO_ENABLED': '0',
           'GOPATH': str(temp / 'gopath'), 'GOCACHE': str(temp / 'gocache'),
           'GOPROXY': 'https://proxy.golang.org', 'GOSUMDB': 'sum.golang.org'}
    subprocess.run([str(temp / 'go' / 'bin' / 'go'), 'install', '-trimpath',
                    f'github.com/bitnami/sealed-secrets/cmd/kubeseal@v{version}'], env=env, check=True)


try:
    if os.environ.get('KUBESEAL_FROM_GO_PROXY'):
        raise OSError('KUBESEAL_FROM_GO_PROXY is set')
    from_release()
except OSError as error:
    print(f'kubeseal release download failed ({error}); building v{version} from the Go module proxy')
    from_go_proxy()
with open(os.environ['GITHUB_PATH'], 'a') as f:
    f.write(str(folder) + '\n')
