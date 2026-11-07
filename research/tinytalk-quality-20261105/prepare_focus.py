#!/usr/bin/env python3
"""Learn a short answer-content span before unchanged public speech."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil

from common import core, load_model, quantize
from rebalance import compact_tokenizer


def main():
    import torch
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', default='before-focus')
    p.add_argument('--output-model', default='focus-init')
    p.add_argument('--output-data', default='data')
    p.add_argument('--model-only', action='store_true')
    p.add_argument('--device', default='cpu')
    p.add_argument('--seed', type=int, default=765109)
    args = p.parse_args(); out = Path(args.output_model)
    if not out.exists():
        model, tok, _ = load_model(args); model.eval().requires_grad_(False)
        old = model.transformer.wte.weight.detach().clone(); old_vocab = len(tok)
        ids = tok.encode(' answer', add_special_tokens=False)
        specials = [f'<|tt_intent:{name}|>' for name in model.config.tinytalk_intent_token_ids]
        specials += [f'<|tt_type:{name}|>' for name in model.config.tinytalk_answer_type_token_ids]
        specials += ['<|tt_say|>']
        assert tok.add_special_tokens({'additional_special_tokens': specials}) == 1
        model.resize_token_embeddings(len(tok), mean_resizing=False)
        say = tok.convert_tokens_to_ids('<|tt_say|>')
        with torch.no_grad(): model.transformer.wte.weight[say].copy_(quantize.dequantized(old[ids]).mean(0))
        assert torch.equal(old, model.transformer.wte.weight[:old_vocab])
        assert model.lm_head.weight is model.transformer.wte.weight
        model.config.tinytalk_answer_focus_separator_id = say
        model.config.tinytalk_answer_focus_max_tokens = 10
        model.config.tinytalk_answer_focus_description = 'Short answer keywords; not an explanation; excluded from public history'
        out.mkdir(); model.save_pretrained(out, safe_serialization=True); tok.save_pretrained(out)
        quantize.copy_notices(args.model, out)
        extra = Path(args.model) / 'LANGUAGE_DATA.md'
        if extra.exists(): shutil.copyfile(extra, out / extra.name)
        table = compact_tokenizer(tok, out / 'tokenizer.ttbpe')
        meta = quantize.export(model, out / 'model.ttq4', {'recipe': 'Short learned answer-content span initializer',
            'source_sha256': core.digest(Path(args.model) / 'model.safetensors')})
        total = meta['file_bytes'] + table['file_bytes'] + 1048576 + 262144
        assert total < 8388608
        core.save(out / 'focus-model.json', {'source_sha256': core.digest(Path(args.model) / 'model.safetensors'),
            'ordinary_embeddings_exact': True, 'old_vocab': old_vocab, 'new_vocab': len(tok),
            'parameters': sum(v.numel() for v in model.parameters()), 'total_design_bytes': total,
            'remaining_from_8mib': 8388608 - total, 'reserve_bytes': 262144, 'native_runtime_measured': False})
    if args.model_only: return
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(out, local_files_only=True, trust_remote_code=False)
    data = Path(args.output_data); assert not data.exists(); data.mkdir()
    manifest = json.loads(Path('focus-labels/manifest.json').read_text())
    assert not manifest['probe_only'] and manifest['source_sha256'] == core.digest('base-data/train.jsonl')
    assert manifest['sha256'] == core.digest('focus-labels/labels.jsonl')
    labels = {r['id']: r for r in core.read_rows('focus-labels/labels.jsonl')}
    known_bad = set()
    for probe in ['focus-probe', 'focus-probe-compact2']:
        for name in ['answer-audit.json', 'keyword-audit.json']:
            path = Path(probe) / name
            if path.exists(): known_bad.update(g['id'] for g in json.loads(path.read_text())['details'] if not g['pass'])
    full_audit = json.loads(Path('focus-labels/keyword-audit.json').read_text())
    assert full_audit['labels_sha256'] == manifest['sha256'] and full_audit['pass_rate'] >= .95
    known_bad.update(g['id'] for g in full_audit['details'] if not g['pass'])
    rows = []; used = set(); skipped = []; output_too_long = []; counts = Counter()
    for source in core.read_rows('base-data/train.jsonl'):
        row = dict(source)
        if row['kind'] == 'replay': rows.append(row); continue
        match = re.fullmatch(r'<\|tt_intent:(\w+)\|><\|tt_type:\w+\|>\s*(.*)', row['target'], flags=re.S)
        assert match, row['id']
        act, body = match.groups()
        if row['id'] not in labels:
            assert row['id'] in manifest['unlabelable_rows_excluded']; continue
        label = labels[row['id']]; used.add(row['id'])
        if row['id'] in known_bad: continue
        focus = label['focus']; form = label['answer_type']
        assert focus in body or (focus == 'unknown' and form == 'unknown')
        n = len(tok.encode(' ' + focus, add_special_tokens=False))
        if n > 10:
            skipped.append({'id': row['id'], 'focus_tokens': n}); continue
        target = f'<|tt_intent:{act}|><|tt_type:{form}|> {focus}<|tt_say|> ' + body
        if len(tok.encode(' ' + target, add_special_tokens=False)) + 1 > 40:
            output_too_long.append(row['id']); continue
        # Keep the same forty-token inference budget. Exclude and report any
        # reference whose added keyword span would exceed it; never cut speech.
        row.update(target=target, plain_target=body, answer_type=form, answer_focus=focus)
        rows.append(row); counts[form] += 1
    assert used == set(labels)
    path = data / 'train.jsonl'; path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    core.save(data / 'manifest.json', {'rows': len(rows), 'sha256': core.digest(path),
        'source_sha256': core.digest('base-data/train.jsonl'), 'labels': manifest,
        'too_long_focus_rows_excluded': skipped, 'answer_types': dict(counts),
        'too_long_generated_targets_excluded': output_too_long,
        'known_failed_supervision_rows_excluded': sorted(known_bad),
        'kinds': dict(Counter(r['kind'] for r in rows)), 'contexts_and_spoken_targets_unchanged': True,
        'format': 'Learned intent, learned type, short answer keywords, private separator, unchanged spoken text',
        'decoding_max_new_tokens': 40, 'reserved_audit3_opened': False})
    print(json.dumps({'rows': len(rows), 'focus_too_long': len(skipped), 'model': str(out)}), flush=True)


if __name__ == '__main__': main()
