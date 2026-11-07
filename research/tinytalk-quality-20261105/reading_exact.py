#!/usr/bin/env python3
"""Teacher-free strict reading diagnostic; separate from the conversation quality gate."""
import argparse
from collections import defaultdict
from pathlib import Path
import re
from common import core, decode, load_model, quantize


def normalize(value):
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', value.lower().replace("don't", 'do not')).split())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--suite', default='babi-probe/test.jsonl')
    p.add_argument('--output', required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--seed', type=int, default=84119)
    args = p.parse_args()
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    quantize.roundtrip(model)
    cases = core.read_rows(args.suite)
    replies = decode(model, tokenizer, cases, device)
    details = []
    groups = defaultdict(list)
    for case, reply in zip(cases, replies):
        accepted = normalize(reply['reply']) == normalize(case['plain_target'])
        details.append({'id':case['id'], 'task':case['task'], 'target':case['plain_target'],
            'reply':reply['reply'], 'exact':accepted})
        groups[case['task']].append(accepted)
    result = {'method':'Strict normalized exact match to the trained canonical short-answer format; no teacher API',
        'not_the_conversation_quality_gate':True, 'model_sha256':core.digest(Path(args.model) / 'model.safetensors'),
        'suite_sha256':core.digest(args.suite), 'total':len(details), 'passed':sum(r['exact'] for r in details),
        'per_task':{k:{'passed':sum(v), 'total':len(v)} for k,v in groups.items()},
        'details':details, 'reserved_chat_audit_opened':False, 'packed_q4_arithmetic':True}
    core.save(args.output, result)
    print({k:v for k,v in result.items() if k != 'details'}, flush=True)


if __name__ == '__main__':
    main()
