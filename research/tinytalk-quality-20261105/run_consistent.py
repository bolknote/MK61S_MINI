#!/usr/bin/env python3
"""Train the consistent-response corpus from the best preserved-language checkpoint."""
import json
from pathlib import Path
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from run_remote import ROOT, ORIGIN, container, command, status


def main():
    status('waiting_for_training_data')
    deadline = time.monotonic() + 1800
    while not (ROOT / 'consistent/manifest.json').exists():
        if time.monotonic() > deadline:raise TimeoutError('Consistent generation deadline')
        time.sleep(5)
    command(['python3', '-u', 'prepare_consistent.py', '--skills', str(ROOT.parent / 'round6/data')], 'prepare.log', 900)
    while not (ROOT / 'format-probe/comparison.json').exists() or len(json.loads((ROOT / 'format-probe/comparison.json').read_text())) != 2:
        if time.monotonic() > deadline:raise TimeoutError('Format comparison deadline')
        time.sleep(5)
    comparison = json.loads((ROOT / 'format-probe/comparison.json').read_text())
    # Select decoder behavior only on development data; the fresh audit stays closed.
    structured = comparison['True']['selection_score'] > comparison['False']['selection_score']
    source = Path(ORIGIN['previous_model']);initial = ROOT / 'consistent-init'
    shutil.copytree(source, initial)
    config = json.loads((initial / 'config.json').read_text())
    config['tinytalk_structured_intent_decoding'] = structured
    (initial / 'config.json').write_text(json.dumps(config, indent=2))
    table = ROOT.parent / 'round6/grounded/tokenizer.ttbpe'
    if not table.exists():table = ROOT.parent / 'round6/conversation-init/tokenizer.ttbpe'
    shutil.copyfile(table, initial / 'tokenizer.ttbpe')
    status('training', steps=10000, batch_size=64, structured_intent_decoding=structured,
           arms=['consistent-top4', 'consistent-top6'])
    def worker(arm):
        gpu, layers = (0, 4) if arm == 'consistent-top4' else (1, 6)
        command(container(gpu, 'train.py', '--mode', 'sft', '--model', 'consistent-init', '--output', arm,
                          '--steps', '10000', '--batch-size', '64', '--lr', '1e-5', '--eval-every', '1000',
                          '--qat-start', '1', '--embedding-lr-scale', '1', '--replay-fraction', '0', '--kl', '0.01',
                          '--intent-weight', '4', '--uniform-groups', '--freeze-word-embeddings', '--train-last-layers', str(layers)),
                arm + '.log', 10800)
    arms = ['consistent-top4', 'consistent-top6']
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker, arms))
    candidates = []
    for gpu, arm in enumerate(arms):
        report = json.loads((ROOT / arm / 'training.json').read_text())
        chosen = next((row for row in report['history'] if row['step'] == report['best_step']), report['baseline'])
        candidates.append({'mode': arm, 'step': report['best_step'], 'goal_met': chosen['goal_met'], 'score': chosen['selection_score'],
                           'acceptable': chosen['direct']['pass_rate'], 'context': chosen['context_pass_rate'], 'multi_turn': chosen['multi_turn']['pass_rate']})
        command(container(gpu, 'quantize.py', '--model', f'{arm}/best', '--output', f'{arm}/model.ttq4', '--report', f'{arm}/packed.json'), arm + '-packed.log')
        shutil.copyfile(initial / 'tokenizer.ttbpe', ROOT / arm / 'tokenizer.ttbpe')
        packed = json.loads((ROOT / arm / 'packed.json').read_text());table_bytes = (ROOT / arm / 'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table_bytes + 1048576 + 262144
        assert total < 8388608
        (ROOT / arm / 'memory-budget.json').write_text(json.dumps({'packed_bytes': packed['file_bytes'], 'tokenizer_bytes': table_bytes,
                'fp16_kv_context128_bytes': 1048576, 'reserve_bytes': 262144, 'total_design_bytes': total,
                'remaining_from_8mib': 8388608 - total, 'native_runtime_measured': False}, indent=2))
    candidates.sort(key=lambda row: (row['goal_met'], row['score']), reverse=True)
    (ROOT / 'selection.json').write_text(json.dumps({'selected': candidates[0], 'candidates': candidates, 'test_opened': False}, indent=2))
    status('development_target_met' if candidates[0]['goal_met'] else 'needs_next_iteration', selected=candidates[0])


if __name__ == '__main__':
    try:main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}');raise
