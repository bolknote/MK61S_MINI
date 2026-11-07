#!/usr/bin/env python3
"""Continue weak broad conversation with explicit reading practice, preserving Q4 and the memory budget."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import time
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--after-failed-audit', action='store_true')
    args = p.parse_args()
    origin = json.loads((ROOT / 'grounded-origin.json').read_text())
    previous = Path(origin['conversation_round'])
    status('waiting_for_conversation_comparison')
    deadline = time.monotonic() + 14400
    while not (previous / 'selection.json').exists():
        if time.monotonic() > deadline:
            raise TimeoutError('Conversation comparison not ready')
        time.sleep(5)
    selected = json.loads((previous / 'selection.json').read_text())['selected']
    if selected['goal_met'] and not args.after_failed_audit:
        status('parent_requires_independent_audit', parent=selected)
        return
    shutil.copytree(previous / selected['mode'] / 'best', ROOT / 'source-model')
    shutil.copyfile(previous / selected['mode'] / 'tokenizer.ttbpe', ROOT / 'source-model/tokenizer.ttbpe')
    shutil.copytree(previous / 'data', ROOT / 'base-data')
    license = (ROOT / 'babi-data/LICENSE-DATA.txt').read_text()
    notice = ROOT / 'source-model/NOTICE.md'
    notice.write_text((notice.read_text() if notice.exists() else '') +
        '\n\nAdditional training-data attribution: Facebook bAbI tasks, CC BY 3.0.\n'
        'Weston et al. (2015), Towards AI-Complete Question Answering: A Set of Prerequisite Toy Tasks.\n'
        'https://parl.ai/downloads/babi/babi.tar.gz\n'
        'Adaptations: shorter complete context windows, conversational renderings, gender-consistent entity renaming.\n'
        'The following license covers this dataset, not the original model weights.\n\n' + license)
    command(container(0, 'combine_grounded.py'), 'combine-data.log', 600)
    command(container(0, 'evaluate_babi.py', '--model', 'source-model', '--output', 'babi-baseline'),
        'babi-baseline.log', 1200)
    status('training_grounded_conversation', steps=12000, batch_size=128,
        arms=['grounded40', 'grounded65'], parent=selected, new_chat_audit_opened=False)
    items = [(0, 'grounded40', .4, .45), (1, 'grounded65', .65, .2)]
    def worker(item):
        gpu, label, grounded, natural = item
        command(container(gpu, 'train.py', '--mode', 'sft', '--model', 'source-model', '--output', label,
            '--steps', '12000', '--batch-size', '128', '--lr', '1.5e-5', '--eval-every', '1000',
            '--qat-start', '1', '--embedding-lr-scale', '.3', '--replay-fraction', '0',
            '--kl', '0.005', '--intent-weight', '1', '--natural-fraction', str(natural),
            '--grounded-fraction', str(grounded), '--example-balanced-loss', '--train-last-layers', '8',
            '--opened-audit-development', '--balanced-selection',
            '--additional-development', 'suite/opened-audit2.jsonl',
            '--additional-scenarios', 'suite/opened-audit2-scenarios.json'), label + '.log', 14400)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(worker, items))
    candidates = []
    for gpu, label, _, _ in items:
        report = json.loads((ROOT / label / 'training.json').read_text())
        chosen = next((v for v in report['history'] if v['step'] == report['best_step']), report['baseline'])
        candidates.append({'mode':label, 'step':report['best_step'], 'goal_met':chosen['goal_met'],
            'score':chosen['selection_score'], 'bottleneck_ratio':bottleneck(chosen),
            'development_partitions':chosen['development_partitions'],
            'two_consecutive_goal_checks':bool(report.get('early_stop_reason'))})
        command(container(gpu, 'pack_candidate.py', '--model', label + '/best', '--output', label + '/model.ttq4',
            '--report', label + '/packed.json'), label + '-packed.log')
        shutil.copyfile(ROOT / 'source-model/tokenizer.ttbpe', ROOT / label / 'tokenizer.ttbpe')
        packed = json.loads((ROOT / label / 'packed.json').read_text())
        table = (ROOT / label / 'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table + 1048576 + 262144
        assert total < 8388608
        (ROOT / label / 'memory-budget.json').write_text(json.dumps({'packed_bytes':packed['file_bytes'],
            'tokenizer_bytes':table, 'fp16_kv_context128_bytes':1048576, 'reserve_bytes':262144,
            'total_design_bytes':total, 'remaining_from_8mib':8388608 - total, 'native_runtime_measured':False}, indent=2))
        command(container(gpu, 'evaluate_babi.py', '--model', label + '/best', '--output', label + '/babi-diagnostic'),
            label + '-babi.log', 1200)
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
