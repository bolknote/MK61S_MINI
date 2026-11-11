"""Verify frozen data, immutable inputs, exact Q4 export and native diagnoses."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import struct
import torch
import torch.nn.functional as F
from ao_common import HERE, INITIAL, INITIAL_PACKET, ARMS, DIAG_IDS, read, write, sha
from ao_eval import features
from ao_model import load
from ao_native import Engine, prepare_source, MAX_INPUT_BYTES
from ac_protocol import prompt_ids
from codec_native import native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_export import packet
from native_verify import verify_export


def choose(values):
    selected = []
    for split in ['fresh', 'novel-fresh']:
        rows = values[split]
        for label in range(4):
            selected.extend([(split, r) for r in rows if r['label'] == label][:2])
        longest = max(rows, key=lambda r: len(r['prompt'].encode()))
        if not any(s == split and r['id'] == longest['id'] for s, r in selected):
            selected.append((split, longest))
    return selected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    root = ap.parse_args().root.resolve()
    out = root / 'native'
    out.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    for manifest in ['data-frozen.json', 'prepared.json']:
        for n, digest in json.loads((root / manifest).read_text())['files'].items():
            assert sha(root / n) == digest, n
    prepared = json.loads((root / 'prepared.json').read_text())
    for n, digest in prepared['source_hashes'].items():
        assert sha(HERE / n) == digest, n
    source, tokenizer = load('cpu')
    reference = {n: p.detach().clone() for n, p in source.named_parameters()}
    del source
    prepare_source(root, out, json.loads((CODEC_ROOT / 'codebook-32.json').read_text()))
    spec = importlib.util.spec_from_file_location('ao_exporter', out / 'source/export_model.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    values = {s: [r for g in read(root / (s + '.jsonl')) for r in g['rows']] for s in ['fresh', 'novel-fresh']}
    selected = choose(values)
    models = {}
    results = {}
    for arm in ARMS:
        folder = root / 'export' / arm
        model, exact = verify_export(folder)
        changed = []
        for name, p in model.named_parameters():
            if name == 'model.embed_tokens.weight':
                mask = torch.ones(len(p), dtype=torch.bool)
                mask[DIAG_IDS] = False
                assert torch.equal(p[mask], reference[name][mask]), (arm, name)
                changed = [i for i in DIAG_IDS if not torch.equal(p[i], reference[name][i])]
            else:
                adapted = arm == 'adapt' and name.startswith('model.layers.') and name.endswith((
                    '.self_attn.q_proj.weight', '.self_attn.v_proj.weight', '.mlp.gate_proj.weight',
                    '.mlp.up_proj.weight', '.mlp.down_proj.weight'))
                if not adapted:
                    assert torch.equal(p, reference[name]), (arm, name)
        assert sum(p.numel() for p in model.parameters()) == 3022080
        native_tokenizer(folder / 'hf', out / (arm + '-tokenizer.json'))
        header, payload = packet(folder / 'model.mkqb')
        header['config']['max_position_embeddings'] = 1024
        raw = json.dumps(header, ensure_ascii=False, separators=(',', ':')).encode()
        derived = out / (arm + '-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0' + struct.pack('<I', len(raw)) + raw + payload)
        exporter.export(derived, out / (arm + '-tokenizer.json'), folder / 'model.mka', 'lut')
        models[arm] = model
        results[arm] = {'exact_reload': exact, 'package_bytes': (folder / 'model.mka').stat().st_size,
                        'package_sha256': sha(folder / 'model.mka'), 'changed_private_rows': changed,
                        'all_input_rows_and_unadapted_tensors_bit_identical': True}
    engine = Engine(root)
    for arm in ARMS:
        engine.open(arm)
        model = models[arm]
        h = features(model, tokenizer, [r for _, r in selected])
        cpu = F.linear(h, model.get_input_embeddings().weight[DIAG_IDS]).detach().tolist()
        gpu = {s: {r['id']: r for r in json.loads((root / arm / (s + '.json')).read_text())['details']} for s in values}
        details = []
        for (split, row), c in zip(selected, cpu):
            n = engine.classify(row['prompt'])
            g = gpu[split][row['id']]
            assert n['input_token_ids'] == prompt_ids(tokenizer, row['prompt'])
            prediction = max(range(4), key=c.__getitem__)
            assert n['predicted'] == prediction == g['predicted'], (arm, row['id'], n, c, g)
            cpu_error = max(abs(a - b) for a, b in zip(c, g['logits']))
            native_error = max(abs(a - b) for a, b in zip(n['logits'], g['logits']))
            assert max(cpu_error, native_error) < .01, (arm, cpu_error, native_error)
            details.append({'split': split, 'id': row['id'], 'label': row['label'], 'predicted': prediction,
                            'cpu_logit_error': cpu_error, 'native_logit_error': native_error,
                            'input_tokens': len(n['input_token_ids']), 'input_utf8_bytes': len(row['prompt'].encode())})
        results[arm].update(probes=len(details), cpu_matches=len(details), native_matches=len(details), details=details,
                            cache_bytes=engine.lib.mk_ai_cache(), workspace_bytes=engine.lib.mk_ai_workspace())
        runtime = root / 'export' / arm / 'runtime'
        runtime.mkdir(exist_ok=True)
        for name in ['ao_native.py', 'aj_native.py', 'ac_native.py', 'ao_common.py']:
            shutil.copyfile(HERE / name, runtime / name)
        print(json.dumps({'verified': arm, 'probes': len(details), 'max_native_error': max(d['native_logit_error'] for d in details)}), flush=True)
    pre = json.loads((root / 'preselected.json').read_text())
    shutil.copytree(root / 'export' / pre['selected_arm'], root / 'export/selected-research', dirs_exist_ok=True)
    write(root / 'native-verification.json', {'complete': True, 'models': results,
          'input_rows_and_unadapted_tensors_protected': True, 'shared_weight_buffer_bytes': engine.capacity,
          'source_packet_sha256': sha(INITIAL_PACKET), 'physical_device_measured': False,
          'standalone_classifier_only': True, 'prefix_distillation_not_applied': True})


if __name__ == '__main__':
    main()
