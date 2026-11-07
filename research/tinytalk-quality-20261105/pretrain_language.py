#!/usr/bin/env python3
"""Continue Q4-aware language pretraining of the expanded TinyTalk core."""
import argparse
import json
import math
from pathlib import Path
import time

from common import core, load_model, qat_modules, actual_q4, quantize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="tagged-init")
    parser.add_argument("--data", default="language-data")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=45681)
    parser.add_argument("--tokens", type=int, default=100000000)
    parser.add_argument("--context", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--eval-every", type=int, default=1000)
    args = parser.parse_args()
    import numpy as np
    import torch
    from torch.nn import functional as F
    output = Path(args.output)
    assert not output.exists()
    output.mkdir(parents=True)
    model, tokenizer, device = load_model(args)
    assert args.context == model.config.tinytalk_runtime_context == 128
    data = Path(args.data)
    manifest = json.loads((data / "manifest.json").read_text())
    assert manifest['tokenizer_sha256'] == core.digest(Path(args.model) / 'tokenizer.json')
    training = np.memmap(data / 'train.u16', mode='r', dtype='<u2')
    validation = np.memmap(data / 'validation.u16', mode='r', dtype='<u2')
    assert len(training) == manifest['tokens']['train']
    rng = np.random.default_rng(args.seed)
    blocks = rng.permutation((len(training) - 1) // args.context)
    cursor = 0
    qat = qat_modules(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total_steps = math.ceil(args.tokens / (args.batch_size * args.context))
    def batch(stream, positions):
        arrays = np.stack([stream[int(at):int(at) + args.context + 1] for at in positions]).astype(np.int64)
        return torch.from_numpy(arrays).to(device)
    def loss_for(window):
        hidden = model.transformer(input_ids=window[:, :-1], use_cache=False).last_hidden_state
        logits = model.lm_head(hidden)
        return F.cross_entropy(logits.float().reshape(-1, model.config.vocab_size), window[:, 1:].reshape(-1))
    # Compare the stream alignment with the stock HF causal-label shift.
    sample = batch(validation, [0, args.context + 1])
    model.eval()
    with torch.no_grad():
        custom = float(loss_for(sample))
        stock = float(model(input_ids=sample, labels=sample, use_cache=False).loss)
    assert abs(custom - stock) < 1e-4
    report = {'settings': vars(args), 'source_sha256': core.digest(Path(args.model) / 'model.safetensors'),
              'parameters': sum(p.numel() for p in model.parameters()), 'language_data': manifest,
              'alignment_check': {'stream_loss': custom, 'stock_causal_loss': stock},
              'source_code_sha256': {name: core.digest(Path(__file__).parent / name)
                                     for name in ['pretrain_language.py', 'common.py', 'experiment.py', 'quantize.py', 'legacy_train.py']},
              'conversation_audit_opened': False, 'history': [], 'best_step': 0}
    def validate():
        losses = []
        with actual_q4(model, qat), torch.inference_mode():
            for start in range(0, 65536, 32 * args.context):
                positions = np.arange(start, start + 32 * args.context, args.context)
                window = batch(validation, positions)
                with torch.autocast('cuda', dtype=torch.bfloat16):losses.append(float(loss_for(window)))
        return sum(losses) / len(losses)
    def checkpoint(path, tokens):
        model.config.tinytalk_language_pretraining = {'dataset': 'roneneldan/TinyStories', 'revision': manifest['revision'],
                                                     'token_exposures': tokens, 'context': args.context, 'qat': True}
        quantize.save_qat_checkpoint(model, path, qat);tokenizer.save_pretrained(path);quantize.copy_notices(args.model, path)
        (Path(path) / 'LANGUAGE_DATA.md').write_text('Additional Q4-aware training: https://huggingface.co/datasets/roneneldan/TinyStories\nRevision: ' + manifest['revision'] + '\nLicense: CDLA-Sharing-1.0. See language-data manifest for source hashes and document split.\n')
    torch.cuda.reset_peak_memory_stats()
    best = validate();report['baseline_validation_nll'] = best
    checkpoint(output / 'best', 0)
    print(json.dumps({'validation_step': 0, 'language_nll': best, 'alignment_error': abs(custom - stock)}), flush=True)
    started = time.monotonic()
    for step in range(1, total_steps + 1):
        model.train();optimizer.zero_grad(set_to_none=True)
        if cursor + args.batch_size > len(blocks):
            blocks = rng.permutation((len(training) - 1) // args.context);cursor = 0
        positions = blocks[cursor:cursor + args.batch_size] * args.context;cursor += args.batch_size
        window = batch(training, positions)
        with torch.autocast('cuda', dtype=torch.bfloat16):loss = loss_for(window)
        assert torch.isfinite(loss)
        loss.backward();norm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
        assert torch.isfinite(norm)
        rate = args.lr * min(1., step / 200) * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * step / total_steps)))
        for group in optimizer.param_groups:group['lr'] = rate
        optimizer.step()
        if step == 1 or step % 100 == 0:
            print(json.dumps({'step': step, 'steps': total_steps, 'loss': float(loss.detach()),
                              'tokens': step * args.batch_size * args.context,
                              'seconds': round(time.monotonic() - started, 1),
                              'peak_gpu_bytes': torch.cuda.max_memory_allocated()}), flush=True)
        if step % args.eval_every == 0 or step == total_steps:
            nll = validate();tokens = step * args.batch_size * args.context
            item = {'step': step, 'tokens': tokens, 'language_nll': nll, 'seconds': time.monotonic() - started}
            report['history'].append(item)
            if nll < best:best = nll;report['best_step'] = step;checkpoint(output / 'best', tokens)
            core.save(output / 'training.json', report)
            print(json.dumps({'validation_step': step, 'language_nll': nll, 'best_step': report['best_step']}), flush=True)
    report['token_exposures'] = total_steps * args.batch_size * args.context
    report['seconds'] = time.monotonic() - started
    report['best_sha256'] = core.digest(output / 'best/model.safetensors')
    report['source_unchanged'] = report['source_sha256'] == core.digest(Path(args.model) / 'model.safetensors')
    report['peak_gpu_bytes'] = torch.cuda.max_memory_allocated()
    core.save(output / 'training.json', report)


if __name__ == '__main__':
    main()
