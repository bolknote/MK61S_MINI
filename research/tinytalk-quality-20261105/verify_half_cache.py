#!/usr/bin/env python3
"""Check the planned FP16 KV storage using actual packed weights, without claiming native execution."""
import argparse
from pathlib import Path
from common import core, decode, load_model, quantize


def main():
    import torch
    from transformers.cache_utils import Cache, DynamicLayer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--packed', required=True)
    p.add_argument('--suite', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--seed', type=int, default=84119)
    args = p.parse_args()
    model, tokenizer, device = load_model(args)
    model.eval().requires_grad_(False)
    quantize.restore(model, args.packed)
    cases = core.read_rows(args.suite)
    caches = []
    class HalfKVLayer(DynamicLayer):
        def update(self, key_states, value_states, *extra, **kwargs):
            keys, values = super().update(key_states.half(), value_states.half(), *extra, **kwargs)
            assert self.keys.dtype == self.values.dtype == torch.float16
            # Native kernels could read individual half blocks; this host check upcasts for FP32 attention.
            return keys.float(), values.float()
    def factory():
        cache = Cache(layers=[HalfKVLayer() for _ in range(model.config.num_layers)])
        caches.append(cache)
        return cache
    full = decode(model, tokenizer, cases, device)
    half = decode(model, tokenizer, cases, device, cache_factory=factory)
    matches = sum(a['raw_token_ids'] == b['raw_token_ids'] for a, b in zip(full, half))
    storage = []
    for cache in caches:
        assert len(cache.layers) == model.config.num_layers
        size = sum(t.numel() * t.element_size() for layer in cache.layers for t in [layer.keys, layer.values])
        batch, heads, length, width = cache.layers[0].keys.shape
        expected = 2 * model.config.num_layers * batch * heads * length * width * 2
        assert size == expected
        storage.append({'batch':batch, 'context_tokens':length, 'actual_bytes':size, 'formula_bytes':expected})
    report = {'model_sha256':core.digest(Path(args.model) / 'model.safetensors'),
        'packed_sha256':core.digest(args.packed), 'suite_sha256':core.digest(args.suite),
        'compared':len(cases), 'identical_token_sequences':matches, 'all_match':matches == len(cases),
        'native_runtime_measured':False, 'storage_precision':'FP16', 'attention_arithmetic':'host FP32',
        'storage_checks':storage, 'fp32_cache_replies':full, 'fp16_cache_replies':half}
    core.save(args.output, report)
    print({'compared':len(cases), 'identical_token_sequences':matches, 'native_runtime_measured':False})


if __name__ == '__main__':
    main()
