#!/usr/bin/env python3
"""Test whether frozen vocabulary weights limit transfer to varied dialogue."""
from concurrent.futures import ThreadPoolExecutor
import json
import shutil
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    status('training_unfrozen_vocabulary', steps=8000, arms=['words03', 'words10'], new_audit_opened=False)
    def worker(item):
        gpu, label, scale = item
        command(container(gpu, 'train.py', '--mode', 'sft', '--model', 'source-model', '--output', label,
            '--steps', '8000', '--batch-size', '64', '--lr', '1e-5', '--eval-every', '1000',
            '--qat-start', '1', '--embedding-lr-scale', str(scale), '--replay-fraction', '0',
            '--kl', '0.01', '--intent-weight', '1', '--uniform-groups', '--train-last-layers', '8',
            '--opened-audit-development', '--balanced-selection',
            '--additional-development', 'suite/opened-audit2.jsonl',
            '--additional-scenarios', 'suite/opened-audit2-scenarios.json'), label + '.log', 14400)
    items = [(0, 'words03', .3), (1, 'words10', 1.)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, items))
    candidates = []
    for gpu, label, scale in items:
        report = json.loads((ROOT / label / 'training.json').read_text())
        chosen = next((v for v in report['history'] if v['step'] == report['best_step']), report['baseline'])
        candidates.append({'mode': label, 'step': report['best_step'], 'goal_met': chosen['goal_met'],
            'score': chosen['selection_score'], 'bottleneck_ratio': bottleneck(chosen),
            'development_partitions': chosen['development_partitions']})
        command(container(gpu, 'pack_candidate.py', '--model', label + '/best',
            '--output', label + '/model.ttq4', '--report', label + '/packed.json'), label + '-packed.log')
        shutil.copyfile(ROOT / 'source-model/tokenizer.ttbpe', ROOT / label / 'tokenizer.ttbpe')
        packed = json.loads((ROOT / label / 'packed.json').read_text())
        table = (ROOT / label / 'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table + 1048576 + 262144
        assert total < 8388608
        (ROOT / label / 'memory-budget.json').write_text(json.dumps({'packed_bytes': packed['file_bytes'],
            'tokenizer_bytes': table, 'fp16_kv_context128_bytes': 1048576, 'reserve_bytes': 262144,
            'total_design_bytes': total, 'remaining_from_8mib': 8388608 - total,
            'native_runtime_measured': False}, indent=2))
    candidates.sort(key=lambda v: (v['goal_met'], v['bottleneck_ratio'], v['score']), reverse=True)
    (ROOT / 'selection.json').write_text(json.dumps({'selected': candidates[0], 'candidates': candidates,
        'reserved_audit3_opened': False}, indent=2))
    status('development_target_met' if candidates[0]['goal_met'] else 'needs_next_iteration', selected=candidates[0])


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}')
        raise
