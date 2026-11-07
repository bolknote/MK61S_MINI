#!/usr/bin/env python3
"""Decode every development state probe after Q4 with real FP16 KV storage."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
from common import core, decode, fp16_cache_factory, load_model, quantize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True); p.add_argument('--packed', required=True)
    p.add_argument('--cases', required=True); p.add_argument('--output', required=True)
    p.add_argument('--device', default='cpu'); p.add_argument('--seed', type=int, default=7731)
    args = p.parse_args(); out = Path(args.output); assert not out.exists()
    model, tok, device = load_model(args); quantize.restore(model, args.packed); model.eval().requires_grad_(False)
    cases = core.read_rows(args.cases)
    replies = decode(model, tok, cases, device, cache_factory=fp16_cache_factory(model))
    groups = defaultdict(list)
    for case, reply in zip(cases, replies):
        value = case.get('expected_value')
        if value is None: continue
        has = bool(re.search(r'\b' + re.escape(value) + r'\b', reply['reply'], flags=re.I))
        obsolete = case.get('obsolete_value')
        old = bool(obsolete and re.search(r'\b' + re.escape(obsolete) + r'\b', reply['reply'], flags=re.I))
        label = 'reverse_entity' if case['family'] == 'reverse_entity' else f"echo={case['echo']},pronoun={case['pronoun_update']}"
        if 'temporal_question' in case: label += f",temporal_question={case['temporal_question']}"
        groups[label].append(has and not old)
    summary = {k: {'value_present_without_obsolete': sum(v), 'total': len(v), 'rate': sum(v)/len(v)} for k, v in groups.items()}
    core.save(out, {'cases_sha256': core.digest(args.cases),
        'model_sha256': core.digest(Path(args.model) / 'model.safetensors'), 'packed_sha256': core.digest(args.packed),
        'cache_storage': 'FP16', 'arithmetic': 'host FP32', 'replies': replies,
        'literal_value_diagnostic': summary, 'literal_values_are_not_conversation_quality_scores': True,
        'omitted_context_cases': sum(bool(r['omitted_context_pairs']) for r in replies),
        'bad': sum(r['bad'] for r in replies), 'training_started': False, 'reserved_audit3_opened': False})
    print(json.dumps(summary, indent=2)); print('omitted', sum(bool(r['omitted_context_pairs']) for r in replies))


if __name__ == '__main__': main()
