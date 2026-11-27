#!/usr/bin/env python3
"""Pinned, checksum-verified OpenTofu for credential-free CI validation."""
import hashlib
import io
import os
from pathlib import Path
import urllib.request
import zipfile
version = '1.13.2'
name = f'tofu_{version}_linux_amd64.zip'
base = f'https://github.com/opentofu/opentofu/releases/download/v{version}/'
blob = urllib.request.urlopen(base + name, timeout=60).read()
sums = urllib.request.urlopen(base + f'tofu_{version}_SHA256SUMS', timeout=30).read().decode()
expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == name)
if hashlib.sha256(blob).hexdigest() != expected:
    raise SystemExit('OpenTofu checksum mismatch')
folder = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'self-service-bin'
folder.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(blob)) as archive:
    binary = folder / 'tofu'
    binary.write_bytes(archive.read('tofu'))
    binary.chmod(0o755)
with open(os.environ['GITHUB_PATH'], 'a') as f:
    f.write(str(folder) + '\n')
