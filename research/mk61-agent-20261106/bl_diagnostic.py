"""Paired development-only compact-prompt ablation, with no weight updates."""
import argparse
import collections
import copy
import json
import time
import torch
from transformers import AutoTokenizer
from bl_common import ROOT, PARENT, SOURCES, read, write, rows, sha, check_previous, output_ids, compact_head
from bl_prompt import fit, LIMIT
from bl_vm import CachedVM
from bj_runtime import Session as LongSession
import bj_eval as evaluator
from bj_eval import metrics
from bk_independent_generate import generate as independent
from aq_protocol import prompt_ids
from native_verify import verify_export
from bh_spec import install


class BudgetSession(LongSession):
    tokenizer = None
    compact_mode = False
    created = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self.budgets = []; self.created.append(self)

    def request(self):
        prompt = super().request()
        if self.compact_mode:
            prompt, info = fit(prompt, self.task['task'], self.tokenizer)
        else:
            n = len(prompt_ids(self.tokenizer, prompt)); info = {'level': 0, 'before': n, 'after': n, 'fits': n <= LIMIT}
        self.budgets.append(info); return prompt

    def replan_request(self):
        prompt = super().replan_request()
        if self.compact_mode:
            prompt, info = fit(prompt, self.task['task'], self.tokenizer)
        else:
            n = len(prompt_ids(self.tokenizer, prompt)); info = {'level': 0, 'before': n, 'after': n, 'fits': n <= LIMIT}
        self.budgets.append(info); return prompt


def main(arm):
    check_previous(); install(); protocol = read(ROOT / 'diagnostic-protocol.json')
    assert sha(__file__) == protocol['driver_sha256']
    model, receipt = verify_export(SOURCES[arm]); model.cuda().eval().requires_grad_(False)
    tokenizer = AutoTokenizer.from_pretrained(SOURCES[arm] / 'hf', local_files_only=True); compact_head(model, output_ids(tokenizer))
    goals = rows(PARENT / 'development-clean.jsonl')
    cohort = evaluator.core.choose_runtime(goals, 96, 261111117)
    plans = {r['id']: r for r in read(PARENT / arm / 'development-6000.json')['primary']['records']}
    evaluator.Session = BudgetSession; BudgetSession.tokenizer = tokenizer
    original_mutant = evaluator.core.mutant; mutants = {}
    def mutant(g, vm, kind):
        key = (g['id'], tuple(g['pool']), kind)
        if key not in mutants:
            mutants[key] = original_mutant(g, vm, kind)
        return copy.deepcopy(mutants[key])
    evaluator.core.mutant = mutant
    result = {'arm': arm, 'optimizer_updates': 0, 'models_unchanged': True, 'development_only': True, 'export_verification': receipt}
    vm = CachedVM()
    for mode in ['control', 'compact']:
        BudgetSession.compact_mode = mode == 'compact'; BudgetSession.created = []
        def generate(model, tok, prompts, forced_action=None):
            if mode == 'control':
                return independent(model, tok, prompts, forced_action)
            values = []
            for p in prompts:
                n = len(prompt_ids(tok, p))
                if n > LIMIT:
                    values.append({'action': None, 'body': [], 'codec_error': 'reserved_context_exceeded',
                                   'generated_token_ids': [], 'input_tokens': n})
                else:
                    values += independent(model, tok, [p], forced_action)
            return values
        evaluator.generate = generate
        started = time.monotonic()
        records = evaluator.episodes(model, tokenizer, cohort, plans, vm, 'self')
        for r, s in zip(records, BudgetSession.created):
            r['prompt_budgets'] = s.budgets
        budgets = [b for s in BudgetSession.created for b in s.budgets]
        summary = metrics(records)
        summary['reserved_context_failures'] = sum(any(h.get('generation', {}).get('codec_error') == 'reserved_context_exceeded' for h in r['history']) for r in records)
        result[mode] = {'summary': summary, 'records': records, 'seconds': time.monotonic() - started,
                        'tokens': {'calls': len(budgets), 'max': max(b['after'] for b in budgets),
                                  'mean': sum(b['after'] for b in budgets) / len(budgets),
                                  'levels': dict(collections.Counter(b['level'] for b in budgets))}}
        write(ROOT / 'diagnostic' / arm / (mode + '.json'), result[mode])
        print(json.dumps({'arm': arm, 'mode': mode, 'summary': summary, 'tokens': result[mode]['tokens']}), flush=True)
    result['VM_cache'] = {'hits': vm.hits, 'misses': vm.misses, 'capacity': vm.capacity}
    check_previous(); write(ROOT / 'diagnostic' / arm / 'results.json', result)
    write(ROOT / 'diagnostic' / arm / 'complete.json', {'complete': True, 'optimizer_updates': 0, 'unix': time.time()})


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--arm', choices=['lora', 'full'], required=True); a = p.parse_args()
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False; main(a.arm)
