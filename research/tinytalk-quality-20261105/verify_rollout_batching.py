#!/usr/bin/env python3
"""Verify that batched conversation turns preserve the original sequential dialogue evaluation."""
import argparse
import json
from pathlib import Path
import time
from common import core, load_model, quantize
from evaluate import rollouts, SCENARIOS, TEST_SCENARIOS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--extra-scenarios', required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--seed', type=int, default=84119)
    args = p.parse_args()
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    quantize.roundtrip(model)
    scripts = SCENARIOS + TEST_SCENARIOS + json.loads(Path(args.extra_scenarios).read_text())
    values = {}
    seconds = {}
    for mode, batching in [('sequential',False), ('batched',True)]:
        start = time.monotonic()
        values[mode] = rollouts(model, tokenizer, device, scripts, 'verification', batched=batching)
        seconds[mode] = time.monotonic() - start
    first, second = values.values()
    matches = sum(a['raw_token_ids'] == b['raw_token_ids'] for a,b in zip(first[1], second[1]))
    report = {'model_sha256':core.digest(Path(args.model) / 'model.safetensors'),
        'device':device, 'replies':len(first[1]), 'identical_token_sequences':matches,
        'all_reply_metadata_identical':first[1] == second[1], 'case_contexts_identical':first[0] == second[0],
        'histories_identical':first[2] == second[2], 'seconds':seconds,
        'scenarios':len(scripts), 'reserved_audit3_opened':False}
    core.save(args.output, report)
    assert first == second
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
