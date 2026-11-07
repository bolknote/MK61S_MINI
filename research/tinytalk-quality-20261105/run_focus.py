#!/usr/bin/env python3
"""Train answer-content keywords and public speech; retain original quality gates."""
import json
import os
import shutil
import sys
import time
from common import core
from run_remote import ROOT, container, command, status
from run_preferences import bottleneck


def main():
    previous = ROOT.parent / 'round19'; other = ROOT.parent / 'round19b'
    deadline = time.monotonic() + 14400
    status('waiting_for_answer_keyword_labels_and_student_comparison')
    while True:
        for parent in [previous, other]:
            p = parent / 'selection.json'
            if p.exists():
                selected = json.loads(p.read_text())['selected']
                if selected['goal_met'] and selected.get('two_consecutive_goal_checks'):
                    status('parent_requires_precision_validation', parent=str(parent), selected=selected); return
        ready = all(p.exists() for p in [ROOT / 'focus-labels/manifest.json',
            ROOT / 'focus-labels/keyword-audit.json', previous / 'selection.json', other / 'selection.json'])
        if ready: break
        if time.monotonic() > deadline: raise TimeoutError('Keyword labels or student comparison did not finish')
        time.sleep(5)
    proof = json.loads((ROOT / 'focus-preflight.json').read_text())
    wire = proof['typed_wire_format_check']
    assert all(wire[k] for k in ['all_private_headers_valid', 'answer_keywords_excluded_from_public_reply',
        'keyword_values_remain_copyable_in_speech', 'keyword_length_bound_enforced', 'no_eos_before_speech'])
    assert proof['frozen_packed_payload_bytes_identical'] == 6022240
    labels = json.loads((ROOT / 'focus-labels/manifest.json').read_text())
    audit = json.loads((ROOT / 'focus-labels/keyword-audit.json').read_text())
    assert audit['pass_rate'] >= .95 and audit['labels_sha256'] == labels['sha256']
    assert not (ROOT / 'focused').exists()
    if not (ROOT / 'before-focus').exists():
        shutil.copytree(previous / 'typed/best', ROOT / 'before-focus', copy_function=os.link)
        shutil.copyfile(previous / 'typed/tokenizer.ttbpe', ROOT / 'before-focus/tokenizer.ttbpe')
    parent_sha = core.digest(ROOT / 'before-focus/model.safetensors')
    assert parent_sha == core.digest(previous / 'typed/best/model.safetensors')
    status('preparing_learned_answer_keywords', source_sha256=parent_sha)
    if not (ROOT / 'data/manifest.json').exists(): command(container(0, 'prepare_focus.py'), 'prepare-focus.log', 1200)
    meta = json.loads((ROOT / 'focus-init/focus-model.json').read_text())
    assert meta['parameters'] == 11636480 and meta['ordinary_embeddings_exact']
    merged = json.loads((ROOT / 'data/manifest.json').read_text())
    assert merged['sha256'] == core.digest(ROOT / 'data/train.jsonl')
    snapshot = ROOT / 'source'; snapshot.mkdir()
    for path in ROOT.glob('*.py'): shutil.copyfile(path, snapshot / path.name)
    status('training_learned_answer_keywords', steps=12000, parameters=11636480,
        effective_trainable_elements=1058560, inherited_elements_frozen=10577920,
        keywords_max_tokens=10, total_generation_max_tokens=40, teacher_label_audit=audit['pass_rate'])
    command(container(0, 'train.py', '--mode', 'sft', '--model', 'focus-init', '--output', 'focused',
        '--steps', '12000', '--batch-size', '128', '--lr', '3e-5', '--eval-every', '1000', '--qat-start', '1',
        '--expanded-mlp-only', '--embedding-lr-scale', '1', '--replay-fraction', '0', '--kl', '.01', '--intent-weight', '2',
        '--branched-fraction', '.3', '--prefix-fraction', '.15', '--natural-fraction', '.15',
        '--grounded-fraction', '.05', '--contrastive-fraction', '.25', '--example-balanced-loss',
        '--train-last-layers', '8', '--opened-audit-development', '--balanced-selection',
        '--additional-development', 'suite/opened-audit2.jsonl',
        '--additional-scenarios', 'suite/opened-audit2-scenarios.json'), 'focused.log', 14400)
    report = json.loads((ROOT / 'focused/training.json').read_text()); assert report['inherited_parameters_verified']
    chosen = next((v for v in report['history'] if v['step'] == report['best_step']), report['baseline'])
    item = {'mode': 'focused', 'step': report['best_step'], 'goal_met': chosen['goal_met'],
        'score': chosen['selection_score'], 'bottleneck_ratio': bottleneck(chosen),
        'development_partitions': chosen['development_partitions'],
        'two_consecutive_goal_checks': bool(report.get('early_stop_reason'))}
    command(container(0, 'pack_candidate.py', '--model', 'focused/best', '--output', 'focused/model.ttq4',
        '--report', 'focused/packed.json'), 'focused-packed.log')
    shutil.copyfile(ROOT / 'focus-init/tokenizer.ttbpe', ROOT / 'focused/tokenizer.ttbpe')
    packed = json.loads((ROOT / 'focused/packed.json').read_text()); table = (ROOT / 'focused/tokenizer.ttbpe').stat().st_size
    total = packed['file_bytes'] + table + 1048576 + 262144; assert total < 8388608
    core.save(ROOT / 'focused/memory-budget.json', {'packed_bytes': packed['file_bytes'], 'tokenizer_bytes': table,
        'fp16_kv_context128_bytes': 1048576, 'reserve_bytes': 262144, 'total_design_bytes': total,
        'remaining_from_8mib': 8388608-total, 'native_runtime_measured': False})
    operations = ROOT / 'operations'; operations.mkdir(exist_ok=True)
    command([sys.executable, 'verify_inherited_payload.py', '--source', str(ROOT.parent / 'round17/expanded/model.ttq4'),
        '--trained', 'focused/model.ttq4', '--output', 'operations/inherited-packed-after-training.json'], 'inheritance.log', 120)
    core.save(ROOT / 'selection.json', {'selected': item, 'candidates': [item], 'comparison_finished': True,
                                      'reserved_audit3_opened': False})
    status('development_target_met' if item['goal_met'] and item['two_consecutive_goal_checks'] else 'needs_next_iteration', selected=item)


if __name__ == '__main__':
    try: main()
    except BaseException as error:
        status('failed', error=f'{type(error).__name__}: {error}'); raise
