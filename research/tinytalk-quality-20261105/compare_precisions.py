#!/usr/bin/env python3
"""Compare raw and packed-Q4 arithmetic on the already observed broad development set."""
import argparse
import inspect
import json
from pathlib import Path
from common import core, decode, load_model, quantize
from grade import grade


def main():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--llama', action='store_true')
    p.add_argument('--device', default='cuda')
    p.add_argument('--seed', type=int, default=84119)
    args = p.parse_args()
    torch.set_num_threads(4)
    torch.manual_seed(args.seed)
    out = Path(args.output)
    assert not out.exists()
    out.mkdir(parents=True)
    if args.llama:
        tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True, trust_remote_code=False)
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = 'left'
        model = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True, trust_remote_code=False,
            dtype=torch.float32, attn_implementation='eager').to(args.device)
        def replies(cases):
            result = []
            for start in range(0, len(cases), 8):
                group = cases[start:start + 8]
                texts = []
                for case in group:
                    messages = [dict(m) for m in case['messages']]
                    def render():
                        return tokenizer.apply_chat_template([{'role':'system', 'content':
                            'You are TinyTalk, an AI text chatbot. Answer in under 15 words.'}] + messages,
                            tokenize=False, add_generation_prompt=True)
                    while len(tokenizer.encode(render(), add_special_tokens=False)) + 48 > 192:
                        assert len(messages) >= 3
                        del messages[:2]
                    texts.append(render())
                inputs = tokenizer(texts, padding=True, add_special_tokens=False, return_tensors='pt').to(args.device)
                options = dict(max_new_tokens=48, do_sample=False, use_cache=True,
                    pad_token_id=tokenizer.eos_token_id, eos_token_id=tokenizer.eos_token_id)
                if 'logits_to_keep' in inspect.signature(model.forward).parameters:
                    options['logits_to_keep'] = 1
                generated = model.generate(**inputs, **options)[:, inputs.input_ids.shape[1]:].tolist()
                for case, tokens in zip(group, generated):
                    ended = tokenizer.eos_token_id in tokens
                    if ended:
                        tokens = tokens[:tokens.index(tokenizer.eos_token_id) + 1]
                    result.append({'id':case['id'], 'reply': tokenizer.decode(tokens, skip_special_tokens=True).strip(),
                        'ended_with_eos':ended, 'raw_token_ids':tokens})
            return result
    else:
        model, tokenizer, _ = load_model(args)
        def replies(cases):
            return decode(model, tokenizer, cases, args.device)
    model.eval().requires_grad_(False)
    path = Path('suite/opened-audit2.jsonl')
    cases = core.read_rows(path)
    report = {'source_sha256':core.digest(Path(args.model) / 'model.safetensors'),
        'development_sha256':core.digest(path), 'reserved_audit_opened':False,
        'execution':'Dequantized host FP32 arithmetic; not a native device runtime'}
    with torch.inference_mode():
        for mode in ['fp32', 'q4']:
            if mode == 'q4':
                packed = quantize.export(model, out / 'model.ttq4', {'purpose':'Precision diagnosis'})
                quantize.restore(model, out / 'model.ttq4')
                report['packed_bytes'] = packed['file_bytes']
            decoded = replies(cases)
            grades = grade(cases, decoded, out / 'grade-cache')
            report[mode] = {'grades':grades, 'replies':decoded}
            core.save(out / 'comparison.json', report)
            print(json.dumps({'precision':mode, 'pass_rate':grades['pass_rate']}), flush=True)


if __name__ == '__main__':
    main()
