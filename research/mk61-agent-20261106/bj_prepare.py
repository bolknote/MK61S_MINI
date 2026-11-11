"""Freeze new data, parents, protocol and selection before either training run."""
import collections
import json
import shutil
import time
import torch
from transformers import AutoTokenizer
from bj_common import ROOT, PARENT, PRIORS, SOURCES, HERE, read, rows, write, sha, signature, body_ids, DEV_NUMBERS, TEST_NUMBERS
from bj_model import agent
from bj_course import Course, encoded, loss
from bc_pools import lesson_layout
from bh_spec import install
from bh_common import check_frozen as previous
from native_export import packet
from be_language import paths3
from decimal import Decimal
from ha_protocol import canonical


def main():
    install(); previous(); assert not (ROOT / 'frozen.json').exists()
    for name in ['teacher-frozen.json', 'lessons-frozen.json']:
        for n, digest in read(ROOT / name)['files'].items():
            assert sha(ROOT / n) == digest
    for arm in ['lora', 'full']:
        checkpoint = PARENT / arm / 'last.safetensors'
        assert sha(checkpoint) == read(SOURCES[arm] / 'manifest.json')['selected_checkpoint_sha256']
        shutil.copyfile(checkpoint, ROOT / ('initial-' + arm + '.safetensors'))
    policy = {'steps': 6000, 'checkpoints': [1000, 3000, 6000], 'batch': 32, 'context': 1024,
              'model_seed': 261111120, 'data_seed': 261111121, 'lr_lora': .00008, 'lr_lora_actions': .00008,
              'lr_full': .000015, 'lr_full_embeddings': .0000075, 'weight_decay': .01,
              'draws': '8 NL translation;4 condition-only replan;12 balanced four-way code/spec contrasts;8 retained successful tool rows',
              'all_hypotheses_visible_during_code_decisions': True, 'replan_never_receives_current_code': True,
              'same_six_action_tokens_DIAG04_means_bad_spec': True,
              'typed_missing_RUN_and_domain_replan': True, 'uncompleted_code_candidate_rolled_back': True,
              'checker_acceptance_does_not_prove_Russian_intent': True,
              'separate_metrics_for_false_claims_and_false_accepted_DONE': True,
              'Q4_every_forward': True, 'compute_and_KV': 'FP32', 'same_data_draws_for_both_branches': True,
              'full_trainable': 3022080, 'lora_trainable': 318208,
              'selection': 'raw and typed-self: no increased false accepted DONE/episodes with false DONE claims/corruption, no decreased repairs or completion; typed-self also compared to own legacy-parent loop; protect NL and structured; parent fallback',
              'parent_step_zero_fallback': True, 'closed_used_for_selection': False,
              'mandatory_fixed6000_closed_audit_even_if_selection_falls_back': True,
              'gold_oracle_used_in_training_or_deployable_runtime': False, 'unix': time.time()}
    write(ROOT / 'policy.json', policy)
    tokenizer = AutoTokenizer.from_pretrained(SOURCES['lora'] / 'hf', local_files_only=True)
    assert tokenizer.get_vocab() == AutoTokenizer.from_pretrained(SOURCES['full'] / 'hf', local_files_only=True).get_vocab()
    values = rows(ROOT / 'lessons.jsonl'); valid = []; dropped = collections.Counter()
    for i, row in enumerate(values):
        maximum = max(len(encoded(tokenizer, lesson_layout(row, mode, f'bj:check:{i}:{mode}'))[0]) for mode in ['default', 'full', 'distractors'])
        if maximum <= 1000:
            valid.append(i)
        else:
            dropped[row['origin']] += 1
        if i % 5000 == 0:
            print(json.dumps({'tokenized': i, 'valid': len(valid)}), flush=True)
    assert len(valid) > .75 * len(values)
    write(ROOT / 'valid-ids.json', valid)
    course = Course(tokenizer); batch = course.batch(401, 'cpu')
    indices = torch.cat([batch[-1].nonzero()[:3, 0], (~batch[-1]).nonzero()[:2, 0]])
    batch = tuple(x.index_select(0, indices) for x in batch); head = torch.tensor(body_ids(tokenizer)); initial = {}
    for arm in ['lora', 'full']:
        model = agent(arm, 'cpu'); replica, _ = model.packed(ROOT / ('initial-' + arm + '.mkqb')); del replica
        cpu_payload = packet(ROOT / ('initial-' + arm + '.mkqb'))[1]
        gpu_payload = packet(SOURCES[arm] / 'model.mkqb')[1]
        cpu_differences = sum(a != b for a, b in zip(cpu_payload, gpu_payload))
        # CPU and CUDA low-rank matrix multiplication differ by FP32 rounding.
        # Actual continuation is required to be byte-exact on the B200 below.
        if arm == 'full':
            assert cpu_differences == 0
        gpu_preflight = read(ROOT / 'parent-b200-preflight.json')[arm]
        assert gpu_preflight['B200_master_exact'] and gpu_preflight['B200_Q4_exact']
        with torch.nn.utils.parametrize.cached():
            value, parts = loss(model, batch, head)
        value.backward(); assert torch.isfinite(value) and all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
        initial[arm] = {'trainable': model.trainable_count(), 'CPU_Q4_byte_differences_from_B200_parent': cpu_differences,
                        'B200_initial_Q4_and_master_exact': True, 'finite_gradient': True, 'loss': float(value.detach()), 'parts': parts, 'optimizer_updates': 0}
        del model
    prior = {signature(g['spec']) for p in PRIORS for split in ['train', 'development', 'closed'] for g in rows(p / (split + '-clean.jsonl'))}
    train_signatures = {signature(r['target_spec']) for r in values}
    train_paths = set().union(*(paths3(r['target_spec']['X']) for r in values))
    ast = read(ROOT / 'ast-frozen.json'); held = {tuple(x) for x in ast['dev_triples'] + ast['test_triples']}
    assert not train_paths & held
    banned = {canonical(abs(Decimal(x))) for x in DEV_NUMBERS + TEST_NUMBERS}
    assert not any(any(canonical(abs(Decimal(n))) in banned for n in r['state']['pool']) for r in values)
    for split in ['development', 'closed']:
        keys = {signature(g['spec']) for g in rows(ROOT / (split + '-clean.jsonl'))}
        assert not keys & prior and not keys & train_signatures
    write(ROOT / 'checks.json', {'valid_lessons': len(valid), 'dropped': dict(dropped), 'initial': initial,
          'target_signature_leaks': 0, 'operator_triple_leaks': 0, 'literal_pool_leaks': 0, 'optimizer_updates': 0})
    files = ['plan.json', 'parent-b200-preflight.json', 'ast-frozen.json', 'teacher-frozen.json', 'teacher-audit.jsonl', 'lessons-frozen.json',
             'policy.json', 'valid-ids.json', 'checks.json', 'lessons.jsonl', 'train-clean.jsonl', 'development-clean.jsonl', 'closed-clean.jsonl',
             'initial-lora.safetensors', 'initial-full.safetensors', 'initial-lora.mkqb', 'initial-full.mkqb']
    inherited = read(PARENT / 'frozen.json')['sources']
    sources = {**inherited, **{p.name: sha(p) for p in HERE.glob('bj_*.py')}}
    def assets(arm):
        folder = SOURCES[arm]
        return {str(p.relative_to(folder)): sha(p) for p in [folder / 'model.mkqb', *sorted((folder / 'hf').iterdir())] if p.is_file()}
    write(ROOT / 'frozen.json', {'sources': sources, 'files': {n: sha(ROOT / n) for n in files},
          'parents': {a: assets(a) for a in ['lora', 'full']}, 'SGD_started': False, 'closed_model_generations_seen': False, 'unix': time.time()})
    write(ROOT / 'prepared.json', {'complete': True, 'initial': initial, 'valid_lessons': len(valid), 'optimizer_updates': 0})
    print(json.dumps({'prepared': True, 'valid_lessons': len(valid), 'initial': initial}), flush=True)


if __name__ == '__main__':
    torch.set_num_threads(4); main()
