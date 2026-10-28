#!/usr/bin/env python3
import argparse
import sys
from config import validate, Invalid
p = argparse.ArgumentParser()
p.add_argument('root', nargs='?', default='.')
a = p.parse_args()
try:
    projects = validate(a.root)
except (Invalid, ValueError, TypeError, OSError) as e:
    print(f'Configuration rejected: {e}', file=sys.stderr)
    sys.exit(1)
print(f'Validated {len(projects)} project(s) and all deliveries')
