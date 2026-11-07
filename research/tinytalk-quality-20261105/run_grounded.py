#!/usr/bin/env python3
"""Adapt the expanded language-pretrained core without moving ordinary word embeddings."""
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from run_remote import container, command, status, ROOT, ORIGIN


def main():
    status('refreshing_intents')
    command(container(0, 'refresh_intents.py', '--model', '/previous', '--output', 'conversation-init', '--add-play-move'), 'refresh.log')
    status('training', steps=12000, arms=['grounded','grounded-all'], freeze_word_embeddings=True, variable_value_curriculum=True)
    def worker(arm):
        gpu, layers = (0, 4) if arm == 'grounded' else (1, 8)
        command(container(gpu, 'train.py', '--mode', 'sft', '--model', 'conversation-init', '--output', arm,
                      '--steps', '12000', '--batch-size', '64', '--lr', '2e-5', '--eval-every', '1000',
                      '--qat-start', '1', '--embedding-lr-scale', '1', '--replay-fraction', '0', '--kl', '0.01',
                      '--intent-weight', '4', '--uniform-groups', '--freeze-word-embeddings', '--train-last-layers', str(layers)),
                arm + '.log', 10800)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker, ['grounded','grounded-all']))
    candidates = []
    for gpu, arm in enumerate(['grounded','grounded-all']):
        report = json.loads((ROOT / arm / 'training.json').read_text())
        chosen = next((row for row in report['history'] if row['step'] == report['best_step']), report['baseline'])
        selected = {'mode': arm, 'step': report['best_step'], 'goal_met': chosen['goal_met'],
                'score': chosen['selection_score'], 'acceptable': chosen['direct']['pass_rate'],
                'context': chosen['context_pass_rate'], 'multi_turn': chosen['multi_turn']['pass_rate']}
        candidates.append(selected)
        command(container(gpu, 'quantize.py', '--model', f'{arm}/best', '--output', f'{arm}/model.ttq4', '--report', f'{arm}/packed.json'), arm + '-packed.log')
        shutil.copyfile(ROOT / 'conversation-init/tokenizer.ttbpe', ROOT / arm / 'tokenizer.ttbpe')
        packed = json.loads((ROOT / arm / 'packed.json').read_text())
        table = (ROOT / arm / 'tokenizer.ttbpe').stat().st_size
        total = packed['file_bytes'] + table + 1048576 + 262144
        assert total < 8388608
        (ROOT / arm / 'memory-budget.json').write_text(json.dumps({'packed_bytes': packed['file_bytes'], 'tokenizer_bytes': table,
        'fp16_kv_context128_bytes': 1048576, 'reserve_bytes': 262144, 'total_design_bytes': total,
        'remaining_from_8mib': 8388608 - total, 'native_runtime_measured': False}, indent=2))
    candidates.sort(key=lambda row: (row['goal_met'],row['score']),reverse=True)
    selected = candidates[0]
    (ROOT / 'selection.json').write_text(json.dumps({'selected': selected, 'candidates': candidates, 'test_opened': False}, indent=2))
    status('development_target_met' if selected['goal_met'] else 'needs_next_iteration', selected=selected)


if __name__ == '__main__':
    try:main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}');raise
