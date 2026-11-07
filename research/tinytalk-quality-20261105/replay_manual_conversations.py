#!/usr/bin/env python3
"""Repeat all user turns from a saved manual probe with new actual bot replies."""
import argparse
import json
from pathlib import Path
from common import core, decode, fp16_cache_factory, load_model, quantize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--packed', required=True)
    p.add_argument('--reference-manual', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--fp32-kv', action='store_true', help='Precision control for the same user turns')
    p.add_argument('--seed', type=int, default=7731)
    args = p.parse_args(); output = Path(args.output); assert not output.exists()
    reference = json.loads(Path(args.reference_manual).read_text()); scenarios = []
    for row in reference['samples']:
        if len(row['messages']) == 1: scenarios.append([])
        scenarios[-1].append(row['messages'][-1]['content'])
    model, tok, device = load_model(args); quantize.restore(model, args.packed); model.eval().requires_grad_(False)
    histories = [[] for _ in scenarios]; records = {}; cache_dtypes = set()
    base_factory = fp16_cache_factory(model)
    if args.fp32_kv:
        from transformers.cache_utils import Cache, DynamicLayer
        base_factory = lambda: Cache(layers=[DynamicLayer() for _ in range(model.config.num_layers)])
    caches = []
    def cache_factory():
        cache = base_factory(); caches.append(cache); return cache
    for turn in range(max(map(len, scenarios))):
        active = [i for i, steps in enumerate(scenarios) if turn < len(steps)]
        cases = []
        for i in active:
            histories[i].append({'role': 'user', 'content': scenarios[i][turn]})
            cases.append({'id': f'manual:{i}:{turn}', 'messages': [dict(m) for m in histories[i]]})
        replies = decode(model, tok, cases, device, cache_factory=cache_factory)
        for i, case, reply in zip(active, cases, replies):
            records[i, turn] = dict(case, **{k: v for k, v in reply.items() if k != 'id'})
            histories[i].append({'role': 'assistant', 'content': reply['reply']})
        for cache in caches:
            for layer in cache.layers:
                if layer.keys is not None: cache_dtypes.update([str(layer.keys.dtype), str(layer.values.dtype)])
        caches.clear()
    assert cache_dtypes == {'torch.float32' if args.fp32_kv else 'torch.float16'}
    samples = [records[i, turn] for i, steps in enumerate(scenarios) for turn in range(len(steps))]
    result = {'model_sha256': core.digest(Path(args.model) / 'model.safetensors'),
        'packed_sha256': core.digest(args.packed), 'reference_manual_sha256': core.digest(args.reference_manual),
        'scenarios': len(scenarios), 'samples': samples, 'actual_kv_storage_dtypes': sorted(cache_dtypes),
        'weights': 'Q4', 'attention_arithmetic': 'host FP32', 'all_user_turns_replayed': True,
        'earlier_assistant_replies_generated_by_this_candidate': True,
        'quality_target_established_by_this_probe': False, 'native_runtime_measured': False}
    core.save(output, result)
    for r in samples: print(json.dumps({'id': r['id'], 'question': r['messages'][-1]['content'],
        'reply': r['reply'], 'intent': r['intent_tokens'], 'answer_type': r['answer_type_tokens']}, ensure_ascii=False))


if __name__ == '__main__': main()
