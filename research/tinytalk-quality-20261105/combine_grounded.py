#!/usr/bin/env python3
"""Combine conversational targets with grounded exercises, excluding all diagnostic contexts."""
from collections import Counter
import json
from pathlib import Path
from common import core
from prepare import fingerprint


def main():
    out = Path('data')
    assert not out.exists()
    out.mkdir()
    manifest = json.loads(Path('babi-data/manifest.json').read_text())
    assert manifest['train_sha256'] == core.digest('babi-data/train.jsonl')
    assert manifest['all_supplied_supporting_facts_preserved']
    excluded = {fingerprint(r['messages']) for name in ['dev', 'test', 'opened-audit2']
        for r in core.read_rows(Path('suite') / (name + '.jsonl'))}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-data/test.jsonl'))
    # Only hashes for duplicate exclusion: never generate/grade student answers on the closed audit here.
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    rows = {}
    skipped = 0
    for path in ['babi-data/train.jsonl', 'base-data/train.jsonl']:
        for row in core.read_rows(path):
            key = fingerprint(row['messages'])
            if key in excluded:
                skipped += 1
                continue
            rows.setdefault(key, row)
    path = out / 'train.jsonl'
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows.values()))
    core.save(out / 'manifest.json', {'rows':len(rows), 'sha256':core.digest(path),
        'base_sha256':core.digest('base-data/train.jsonl'), 'babi':manifest,
        'kinds':dict(Counter(r['kind'] for r in rows.values())), 'evaluation_contexts_excluded':skipped,
        'reserved_chat_audit_opened_for_scoring':False,
        'mixture':'Explicit row probabilities; per-example normalized target loss to preserve short factual targets'})


if __name__ == '__main__':
    main()
