#!/usr/bin/env python3
"""Audit all planned actions; reviewed configuration is authoritative, including deletion."""
import collections
import json
import sys

try:
    plan = json.load(sys.stdin)
    changes = plan.get('resource_changes', [])
    if not isinstance(changes, list):
        raise ValueError('resource_changes must be a list')
    counts = collections.Counter()
    replacements = 0
    for resource in changes:
        actions = resource['change']['actions']
        if not isinstance(actions, list) or not actions or any(a not in {'no-op', 'read', 'create', 'update', 'delete', 'forget'} for a in actions):
            raise ValueError('invalid resource actions')
        counts.update(actions)
        replacements += 'delete' in actions and 'create' in actions
except (ValueError, KeyError, TypeError):
    print('Invalid OpenTofu plan JSON', file=sys.stderr)
    sys.exit(1)
print(f"Reviewed plan: {counts['create']} create, {counts['update']} update, {counts['delete']} delete, {replacements} replacement(s). Deletions include stored data.")
