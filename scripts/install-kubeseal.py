#!/usr/bin/env python3
"""Install a pinned kubeseal release, checking its official SHA256SUMS."""
import hashlib
import io
import os
from pathlib import Path
import tarfile
import urllib.request
version = '0.40.0'
name = f'kubeseal-{version}-linux-amd64.tar.gz'
base = f'https://github.com/bitnami-labs/sealed-secrets/releases/download/v{version}/'
blob = urllib.request.urlopen(base + name, timeout=60).read()
sums = urllib.request.urlopen(base + f'sealed-secrets_{version}_checksums.txt', timeout=30).read().decode()
expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
if hashlib.sha256(blob).hexdigest() != expected:
    raise SystemExit('kubeseal checksum mismatch')
folder = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'self-service-bin'
folder.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
    member = next(m for m in archive.getmembers() if m.name in {'kubeseal', './kubeseal'})
    binary = folder / 'kubeseal'
    binary.write_bytes(archive.extractfile(member).read())
    binary.chmod(0o755)
with open(os.environ['GITHUB_PATH'], 'a') as f:
    f.write(str(folder) + '\n')
