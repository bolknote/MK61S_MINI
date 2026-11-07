#!/usr/bin/env python3
"""Apply the unchanged absolute grader to a development-only state diagnostic."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from common import core
from grade import calibrate, grade


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases', required=True); p.add_argument('--replies', required=True); p.add_argument('--output', required=True)
    args = p.parse_args(); out = Path(args.output); assert not out.exists()
    cases = core.read_rows(args.cases); decoded = json.loads(Path(args.replies).read_text())
    assert decoded['cases_sha256'] == core.digest(args.cases)
    assert [c['id'] for c in cases] == [r['id'] for r in decoded['replies']]
    cache = out.parent / 'grader-cache'; calibration = calibrate(cache)
    result = grade(cases, decoded['replies'], cache, workers=12); groups = defaultdict(list)
    for case, g in zip(cases, result['details']):
        label = case['family']
        if case['family'] == 'state_factorial':
            label += f",known={case['known']},echo={case['echo']},pronoun={case['pronoun_update']}"
            if case['known']: label += f",temporal_question={case.get('temporal_question', True)}"
        groups[label].append(g['pass'])
    summary = {k: {'passed': sum(v), 'total': len(v), 'rate': sum(v)/len(v)} for k, v in groups.items()}
    core.save(out, {'model_sha256': decoded['model_sha256'], 'packed_sha256': decoded['packed_sha256'],
        'cases_sha256': core.digest(args.cases), 'reply_file_sha256': core.digest(args.replies),
        'calibration': calibration, 'grading': result, 'groups': summary,
        'purpose': 'Observed development diagnostic; original main quality gates unchanged', 'reserved_audit3_opened': False})
    print(json.dumps({'passed': result['passed'], 'total': result['total'], 'groups': summary}, indent=2), flush=True)


if __name__ == '__main__': main()
