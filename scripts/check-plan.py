#!/usr/bin/env python3
"""Fail closed on deletion/replacement, including resources removed from configuration."""
import json
import sys
plan = json.load(sys.stdin)
if any('delete' in r.get('change', {}).get('actions', []) for r in plan.get('resource_changes', [])):
    print('Refusing deletion/replacement; platform must perform a separate reviewed maintenance operation.', file=sys.stderr)
    sys.exit(1)
print('Plan contains no deletions or replacements')
