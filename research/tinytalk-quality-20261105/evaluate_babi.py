#!/usr/bin/env python3
"""Measure grounded reading separately from conversational quality."""
import argparse
from pathlib import Path
from common import core, decode, load_model, quantize
from grade import grade


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--suite', default='babi-probe/test.jsonl')
    p.add_argument('--output', required=True)
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=84119)
    args = p.parse_args()
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    quantize.roundtrip(model)
    cases = core.read_rows(args.suite)
    for case in cases:
        case['intent'] = 'Use only the stated story. The correct answer is: ' + case['plain_target']
    replies = decode(model, tokenizer, cases, device)
    result = grade(cases, replies, Path(args.output) / 'grade-cache')
    report = {'purpose':'Separate grounded-reading diagnostic; not conversational quality',
        'model_sha256':core.digest(Path(args.model) / 'model.safetensors'), 'suite_sha256':core.digest(args.suite),
        'reserved_chat_audit_opened':False, 'q4':True, 'grades':result, 'replies':replies}
    core.save(Path(args.output) / 'report.json', report)
    print({'pass_rate':result['pass_rate'], 'passed':result['passed'], 'total':result['total']}, flush=True)


if __name__ == '__main__':
    main()
