#!/usr/bin/env python3
"""Replace uncurated branch histories with fully vetted prefixes and final branches."""
from collections import Counter
import json
from pathlib import Path
from common import core
from prepare import fingerprint


def main():
    out=Path('data');assert not out.exists();out.mkdir()
    manifest=json.loads(Path('prefix-data/manifest.json').read_text())
    assert manifest['all_prefix_targets_graded'] and manifest['all_retained_prefixes_passed_both_earlier_reply_checks']
    assert manifest['sha256']==core.digest('prefix-data/train.jsonl')
    assert manifest['clean_branches_sha256']==core.digest('prefix-data/clean-branches.jsonl')
    excluded={fingerprint(r['messages']) for name in ['dev','test','opened-audit2']
        for r in core.read_rows(Path('suite')/(name+'.jsonl'))}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl'))
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-probe/test.jsonl'))
    rows={}
    for name in ['prefix-data/train.jsonl','prefix-data/clean-branches.jsonl','base-data/train.jsonl']:
        for row in core.read_rows(name):
            if name.startswith('base-data') and row['kind'] in ['branched_dialogue','branched_prefix']:continue
            key=fingerprint(row['messages'])
            if key not in excluded:rows.setdefault(key,row)
    path=out/'train.jsonl';path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows.values()))
    core.save(out/'manifest.json',{'rows':len(rows),'sha256':core.digest(path),'prefixes':manifest,
        'kinds':dict(Counter(r['kind'] for r in rows.values())),'base_sha256':core.digest('base-data/train.jsonl'),
        'reserved_audit3_opened_for_scoring':False,'policy':'Every retained branch prefix and target passed the original detailed rubric'})


if __name__=='__main__':main()
