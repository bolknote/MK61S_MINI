#!/usr/bin/env python3
"""Chat with the answer-keyword profile, displaying only its public speech."""
import argparse
import json
from pathlib import Path
import time
from common import core, decode, fp16_cache_factory, load_model, quantize


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True); p.add_argument('--packed', required=True)
    p.add_argument('--json', type=Path); p.add_argument('--prompt')
    p.add_argument('--temperature', type=float, default=0)
    p.add_argument('--fp32-kv', action='store_true'); p.add_argument('--device', default='cpu')
    p.add_argument('--seed', type=int, default=7731)
    args = p.parse_args()
    if not 0 <= args.temperature <= 2: p.error('temperature must be between 0 and 2')
    model, tok, device = load_model(args); model.eval().requires_grad_(False)
    assert getattr(model.config, 'tinytalk_structured_intent_decoding', False)
    quantize.restore(model, args.packed)
    backbone = getattr(model.config, 'tinytalk_backbone', {})
    print(f"CompactChat ({backbone.get('repository', 'local source')}), Q4, "
          f"KV {'FP32' if args.fp32_kv else 'FP16'}, context 128.", flush=True)
    base_factory = fp16_cache_factory(model)
    expected_dtype = 'torch.float16'
    if args.fp32_kv:
        from transformers.cache_utils import Cache, DynamicLayer
        base_factory = lambda: Cache(layers=[DynamicLayer() for _ in range(model.config.num_layers)])
        expected_dtype = 'torch.float32'
    info = {'model_sha256': core.digest(Path(args.model) / 'model.safetensors'),
        'packed_sha256': core.digest(args.packed), 'backbone': backbone,
        'parameters': sum(p.numel() for p in model.parameters()), 'context': 128,
        'total_generation_limit': 40, 'temperature': args.temperature, 'device': device,
        'samples': [], 'native_runtime_measured': False}
    def answer(messages):
        omitted = 0
        while len(tok.encode(core.render(messages), add_special_tokens=False)) + 40 > 128:
            if len(messages) < 3: raise ValueError('Question is too long for the trained context.')
            del messages[:2]; omitted += 1
        if omitted: print('[Старые реплики исключены из контекста.]', flush=True)
        cache = base_factory(); started = time.monotonic()
        case = {'id': f"chat:{len(info['samples'])}", 'messages': [dict(m) for m in messages]}
        row = decode(model, tok, [case], device, temperature=args.temperature, cache_factory=lambda: cache)[0]
        dtypes = sorted({str(layer.keys.dtype) for layer in cache.layers if layer.keys is not None})
        assert dtypes == [expected_dtype]
        info['samples'].append(dict(case, **{k: v for k, v in row.items() if k != 'id'},
            kv_storage_dtypes=dtypes, omitted_context_pairs_before_decode=omitted,
            seconds=time.monotonic() - started))
        print(row['reply'], flush=True)
        return row['reply']
    try:
        if args.prompt is not None:
            answer([{'role': 'user', 'content': args.prompt}])
        else:
            print('Команды: /new — новый разговор, /quit — выход.', flush=True); messages = []
            while True:
                try: question = input('\nВы: ').strip()
                except EOFError: break
                if question == '/quit': break
                if question == '/new': messages.clear(); continue
                if not question: continue
                messages.append({'role': 'user', 'content': question}); print('Модель: ', end='', flush=True)
                try: reply = answer(messages)
                except ValueError as error:
                    messages.pop(); print(error); continue
                messages.append({'role': 'assistant', 'content': reply})
    except KeyboardInterrupt: print('\nОстановлено.')
    finally:
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__': main()
