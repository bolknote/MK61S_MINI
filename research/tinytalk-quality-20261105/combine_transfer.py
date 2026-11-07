#!/usr/bin/env python3
"""Teach attribute-presence transfer while preserving conversation and reading examples."""
from collections import Counter
import json
from pathlib import Path
from common import core
from prepare import fingerprint


def main():
    out = Path('data')
    assert not out.exists()
    out.mkdir()
    cf = json.loads(Path('contrastive-data/manifest.json').read_text())
    assert cf['teacher_audit_pass_rate'] >= .98
    assert cf['sha256'] == core.digest('contrastive-data/train.jsonl')
    excluded = {fingerprint(r['messages']) for name in ['dev','test','opened-audit2']
        for r in core.read_rows(Path('suite') / (name + '.jsonl'))}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-probe/test.jsonl'))
    rows = {}
    for source in ['contrastive-data/train.jsonl','base-data/train.jsonl']:
        for row in core.read_rows(source):
            key = fingerprint(row['messages'])
            if key not in excluded:
                rows.setdefault(key,row)
    path = out / 'train.jsonl'
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows.values()))
    core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'contrastive':cf,
        'base_sha256':core.digest('base-data/train.jsonl'),'kinds':dict(Counter(r['kind']for r in rows.values())),
        'policy':'Canonical short factual answers; balanced presence within the same history; natural conversation retained',
        'reserved_audit3_opened_for_scoring':False})


if __name__ == '__main__':
    main()
