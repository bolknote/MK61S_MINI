#!/usr/bin/env python3
"""Audit canonical fictional-state references using the unchanged detailed grader."""
from collections import Counter
import hashlib
import json
from pathlib import Path

from common import core
from grade import grade
from prepare import fingerprint


def main():
    root=Path('contrastive-data')
    manifest=json.loads((root/'manifest.json').read_text())
    path=root/'train.jsonl'
    assert core.digest(path)==manifest['sha256']
    rows=core.read_rows(path)
    # Exact-match exclusion only; no student inference or audit answer keys.
    excluded={fingerprint(r['messages']) for r in core.read_rows('reserved-audit3/test.jsonl')}
    excluded.update(fingerprint(r['messages']) for r in core.read_rows('babi-probe/test.jsonl'))
    removed={r.get('pair_id',r['id']) for r in rows if fingerprint(r['messages']) in excluded}
    rows=[r for r in rows if r.get('pair_id',r['id']) not in removed]
    balance=Counter()
    for row in rows:
        if 'pair_id' in row:
            balance[row['pair_id']]+=1 if row['known'] else -1
    assert all(v==0 for v in balance.values()),'Preserve entire present/absent pairs'
    manifest['unfiltered_sha256']=manifest['sha256']
    path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    manifest.update(rows=len(rows),sha256=core.digest(path),closed_overlap_groups_excluded=len(removed))
    sample=sorted(rows,key=lambda r:hashlib.sha256(('state-qa:'+r['id']).encode()).hexdigest())[:512]
    (root/'qa-sample.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in sample))
    report=grade(sample,[r['plain_target'] for r in sample],root/'grade-cache',workers=12)
    manifest.update(teacher_audit_pass_rate=report['pass_rate'],teacher_audit_method=report['method'])
    for name,value in [('manifest',manifest),('teacher-audit',report)]:
        temp=root/(name+'.tmp')
        temp.write_text(json.dumps(value,indent=2))
        temp.replace(root/(name+'.json'))
    print(json.dumps({'rows':len(rows),'qa_pass_rate':report['pass_rate'],
        'failed':[v for v in report['details'] if not v['pass']]}),flush=True)


if __name__=='__main__':
    main()
