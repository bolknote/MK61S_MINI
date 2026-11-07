#!/usr/bin/env python3
"""Combine fully vetted complete dialogues with preserved earlier curricula."""
from collections import Counter
import json
from pathlib import Path
from common import core
from prepare import fingerprint


def main():
    out = Path('data')
    assert not out.exists()
    out.mkdir()
    manifest = json.loads(Path('natural-data/manifest.json').read_text())
    assert manifest['all_retained_targets_graded']
    assert manifest['sha256'] == core.digest('natural-data/train.jsonl')
    rows = {}
    for path in ['natural-data/train.jsonl', 'base-data/train.jsonl']:
        for row in core.read_rows(path):
            rows.setdefault(fingerprint(row['messages']), row)
    excluded = {fingerprint(r['messages']) for name in ['dev', 'test', 'opened-audit2']
        for r in core.read_rows(Path('suite') / (name + '.jsonl'))}
    assert not excluded.intersection(rows)
    path = out / 'train.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows.values()))
    core.save(out / 'manifest.json', {'rows':len(rows), 'sha256':core.digest(path),
        'base_sha256':core.digest('base-data/train.jsonl'), 'natural':manifest,
        'kinds':dict(Counter(r['kind'] for r in rows.values())), 'natural_sampling_probability':.7,
        'evaluation_contexts_excluded':True, 'reserved_audit3_opened':False})


if __name__ == '__main__':
    main()
