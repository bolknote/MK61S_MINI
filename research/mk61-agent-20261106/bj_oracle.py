"""Gold-SPEC checker ablation only. It is not an available deployment oracle."""
import argparse
import copy
import json
import time
import torch
from transformers import AutoTokenizer
from bj_common import ROOT, PARENT, SOURCES, read, rows, write, sha, compact_head, output_ids
from bh_spec import install
from native_verify import verify_export
import bh_eval
import ay_eval as core
import bi_rejected_write as paired
from full_isa_vm import FullVM


def main(arm):
    paired.check_inputs()
    install()
    folder = SOURCES[arm]
    model, receipt = verify_export(folder)
    tokenizer = AutoTokenizer.from_pretrained(folder / 'hf', local_files_only=True)
    model.cuda().eval().requires_grad_(False)
    compact_head(model, output_ids(tokenizer))
    goals = rows(PARENT / 'closed-clean.jsonl')
    cohort = core.choose_runtime(goals, 256, 261110117)
    saved = read(PARENT / f'fixed6000_{arm}/closed.json')
    plans = {r['id']: copy.deepcopy(r) for r in saved['primary']['records']}
    for g in cohort:
        plans[g['id']]['declared_spec'] = g['spec']
    paired.ROOT = ROOT / 'oracle'
    started = time.monotonic()
    records = paired.episodes(model, tokenizer, cohort, plans, FullVM(), 'control', arm)
    result = {'arm': arm, 'inference_only': True, 'optimizer_updates': 0,
              'ordinary_unchanged_neural_policy': True, 'gold_spec_in_checker_only': True,
              'initial_model_prompt_unchanged': True, 'posthoc_diagnostic_not_deployment': True,
              'baseline': saved['self']['summary'], 'gold_checker': core.episode_metrics(records),
              'records': records, 'export_verification': receipt,
              'model_sha256': sha(folder / 'model.mkqb'), 'seconds': time.monotonic() - started}
    # Before the first feedback the ordinary actor sees exactly the same input.
    old = {r['id']: r for r in saved['self']['records']}
    assert all(r['history'][0]['prompt'] == old[r['id']]['history'][0]['prompt'] for r in records)
    write(ROOT / 'oracle' / arm / 'results.json', result)
    write(ROOT / 'oracle' / arm / 'complete.json', {'complete': True, 'optimizer_updates': 0, 'unix': time.time()})
    print(json.dumps({k: v for k, v in result.items() if k != 'records'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--arm', choices=['lora', 'full'], required=True); a = p.parse_args()
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False; main(a.arm)
