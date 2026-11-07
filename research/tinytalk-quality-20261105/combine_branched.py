#!/usr/bin/env python3
"""Combine fully screened alternative requests with the acquired state curriculum."""
from collections import Counter
import json
from pathlib import Path
from common import core
from prepare import fingerprint


def main():
    out=Path('data');assert not out.exists();out.mkdir()
    manifest=json.loads(Path('branched-data/manifest.json').read_text())
    assert manifest['all_targets_graded'] and manifest['minimum_branches_per_retained_prefix']>=3
    assert manifest['sha256']==core.digest('branched-data/train.jsonl')
    excluded={fingerprint(r['messages']) for file in ['dev.jsonl','test.jsonl','opened-audit2.jsonl']
        for r in core.read_rows(Path('suite')/file)}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-probe/test.jsonl'))
    rows={}
    for name in ['branched-data/train.jsonl','state-base-data/train.jsonl']:
        for row in core.read_rows(name):
            key=fingerprint(row['messages'])
            if key not in excluded:rows.setdefault(key,row)
    path=out/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows.values()))
    core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'branched':manifest,
        'base_sha256':core.digest('state-base-data/train.jsonl'),
        'kinds':dict(Counter(r['kind'] for r in rows.values())),
        'policy':'Every new target passed original detailed grading; at least three contrasting requests per prefix',
        'reserved_audit3_opened_for_scoring':False})


if __name__=='__main__':main()
