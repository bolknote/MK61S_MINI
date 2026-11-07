#!/usr/bin/env python3
"""Test varied complete dialogues, continuing a chat model or starting from its language core."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import time
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    origin = json.loads((ROOT / 'natural-origin.json').read_text())
    previous = Path(origin['vocabulary_round'])
    deadline = time.monotonic() + 14400
    while not (ROOT / 'data/manifest.json').exists() or not (previous / 'selection.json').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Vetted natural data or vocabulary control not ready')
        time.sleep(5)
    selected = json.loads((previous / 'selection.json').read_text())['selected']
    source = previous / selected['mode'] / 'best'
    shutil.copytree(source, ROOT / 'continued-init')
    shutil.copyfile(ROOT / 'source-model/tokenizer.ttbpe', ROOT / 'continued-init/tokenizer.ttbpe')
    shutil.copytree(origin['language_model'], ROOT / 'fresh-init')
    status('training_complete_natural_dialogues', steps=10000, arms=['continued', 'fresh'],
        source_vocabulary_selection=selected, natural_sampling_probability=.7, new_audit_opened=False)
    def worker(item):
        gpu, label = item
        command(container(gpu, 'train.py', '--mode', 'sft', '--model', label + '-init', '--output', label,
            '--steps', '10000', '--batch-size', '64', '--lr', '2e-5', '--eval-every', '1000',
            '--qat-start', '1', '--embedding-lr-scale', '.3', '--replay-fraction', '0',
            '--kl', '0.01', '--intent-weight', '1', '--natural-fraction', '.7', '--train-last-layers', '8',
            '--opened-audit-development', '--balanced-selection',
            '--additional-development', 'suite/opened-audit2.jsonl',
            '--additional-scenarios', 'suite/opened-audit2-scenarios.json'), label + '.log', 14400)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, enumerate(['continued', 'fresh'])))
    candidates = []
    for gpu, label in enumerate(['continued', 'fresh']):
        report = json.loads((ROOT / label / 'training.json').read_text())
        chosen = next((v for v in report['history'] if v['step'] == report['best_step']), report['baseline'])
        candidates.append({'mode':label, 'step':report['best_step'], 'goal_met':chosen['goal_met'],
            'score':chosen['selection_score'], 'bottleneck_ratio':bottleneck(chosen),
            'development_partitions':chosen['development_partitions']})
        command(container(gpu, 'pack_candidate.py', '--model', label + '/best', '--output', label + '/model.ttq4',
            '--report', label + '/packed.json'), label + '-packed.log')
        shutil.copyfile(ROOT / (label + '-init/tokenizer.ttbpe'), ROOT / label / 'tokenizer.ttbpe')
        packed = json.loads((ROOT / label / 'packed.json').read_text())
        table = (ROOT / label / 'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table + 1048576 + 262144
        assert total < 8388608
        (ROOT / label / 'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],
            'tokenizer_bytes':table, 'fp16_kv_context128_bytes':1048576, 'reserve_bytes':262144,
            'total_design_bytes':total, 'remaining_from_8mib':8388608 - total, 'native_runtime_measured':False}, indent=2))
    candidates.sort(key=lambda v:(v['goal_met'], v['bottleneck_ratio'], v['score']), reverse=True)
    (ROOT / 'selection.json').write_text(json.dumps({'selected':candidates[0], 'candidates':candidates,
        'reserved_audit3_opened':False}, indent=2))
    status('development_target_met' if candidates[0]['goal_met'] else 'needs_next_iteration', selected=candidates[0])


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}')
        raise
