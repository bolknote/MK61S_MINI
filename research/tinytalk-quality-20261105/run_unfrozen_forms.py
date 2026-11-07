#!/usr/bin/env python3
"""Compare gentle full-weight adaptation after the frozen answer-form run."""
import json
import os
import shutil
import time
from common import core
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    previous = ROOT.parent / 'round19'; deadline = time.monotonic() + 14400
    status('waiting_for_complete_answer_form_run')
    while not (previous / 'selection.json').exists():
        if time.monotonic() > deadline: raise TimeoutError('Answer-form run did not complete')
        time.sleep(5)
    parent = json.loads((previous / 'selection.json').read_text())['selected']
    if parent['goal_met'] and parent.get('two_consecutive_goal_checks'):
        status('parent_requires_precision_validation', parent=parent); return
    assert not (ROOT / 'gentle').exists()
    source = previous / 'typed' / 'best'
    if not (ROOT / 'source-model').exists(): shutil.copytree(source, ROOT / 'source-model', copy_function=os.link)
    source_sha = core.digest(ROOT / 'source-model/model.safetensors')
    assert source_sha == core.digest(source / 'model.safetensors')
    shutil.copyfile(previous / 'typed/tokenizer.ttbpe', ROOT / 'source-model/tokenizer.ttbpe')
    snapshot = ROOT / 'source'; snapshot.mkdir()
    for path in ROOT.glob('*.py'): shutil.copyfile(path, snapshot / path.name)
    core.save(ROOT / 'adaptation-origin.json', {'source_sha256': source_sha, 'parent': parent,
        'hypothesis': 'Frozen answer-form features plateau; let attention and core adapt with a lower learning rate',
        'ordinary_embedding_lr_scale': .1, 'all_parameters_trainable': True})
    status('gentle_full_weight_adaptation', steps=8000, lr=3e-6, embedding_lr_scale=.1, kl=.05)
    command(container(0, 'train.py', '--mode', 'sft', '--model', 'source-model', '--output', 'gentle',
        '--steps', '8000', '--batch-size', '128', '--lr', '3e-6', '--eval-every', '1000', '--qat-start', '1',
        '--embedding-lr-scale', '.1', '--replay-fraction', '0', '--kl', '.05', '--intent-weight', '2',
        '--branched-fraction', '.3', '--prefix-fraction', '.15', '--natural-fraction', '.15',
        '--grounded-fraction', '.05', '--contrastive-fraction', '.25', '--example-balanced-loss',
        '--train-last-layers', '8', '--opened-audit-development', '--balanced-selection',
        '--additional-development', 'suite/opened-audit2.jsonl',
        '--additional-scenarios', 'suite/opened-audit2-scenarios.json'), 'gentle.log', 14400)
    report = json.loads((ROOT / 'gentle/training.json').read_text())
    chosen = next((v for v in report['history'] if v['step'] == report['best_step']), report['baseline'])
    item = {'mode': 'gentle', 'step': report['best_step'], 'goal_met': chosen['goal_met'],
        'score': chosen['selection_score'], 'bottleneck_ratio': bottleneck(chosen),
        'development_partitions': chosen['development_partitions'],
        'two_consecutive_goal_checks': bool(report.get('early_stop_reason'))}
    command(container(0, 'pack_candidate.py', '--model', 'gentle/best', '--output', 'gentle/model.ttq4',
        '--report', 'gentle/packed.json'), 'gentle-packed.log')
    shutil.copyfile(ROOT / 'source-model/tokenizer.ttbpe', ROOT / 'gentle/tokenizer.ttbpe')
    packed = json.loads((ROOT / 'gentle/packed.json').read_text()); table = (ROOT / 'gentle/tokenizer.ttbpe').stat().st_size
    total = packed['file_bytes'] + table + 1048576 + 262144; assert total < 8388608
    core.save(ROOT / 'gentle/memory-budget.json', {'packed_bytes': packed['file_bytes'], 'tokenizer_bytes': table,
        'fp16_kv_context128_bytes': 1048576, 'reserve_bytes': 262144, 'total_design_bytes': total,
        'remaining_from_8mib': 8388608-total, 'native_runtime_measured': False})
    core.save(ROOT / 'selection.json', {'selected': item, 'candidates': [item], 'comparison_finished': True,
                                      'reserved_audit3_opened': False})
    status('development_target_met' if item['goal_met'] and item['two_consecutive_goal_checks'] else 'needs_next_iteration', selected=item)


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}'); raise
