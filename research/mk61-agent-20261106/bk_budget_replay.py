"""Targeted correction of cross-prompt truncation in the already opened exam.

No training, new answer selection, input compaction, larger context, or oracle.
The original history is replayed exactly to the first affected generation, then
single-episode decoding continues within the original twelve-action budget.
"""
import argparse
import collections
import copy
import json
import time
import torch
from transformers import AutoTokenizer
from bj_common import ROOT, read, rows, write, sha, output_ids, compact_head, ACTIONS, ACTION_IDS, MAX_TURNS, check_frozen
from bh_spec import install
from bj_runtime import Session
from bj_eval import metrics
from aq_protocol import header_ids
from bk_independent_generate import generate
from native_verify import verify_export
from full_isa_vm import FullVM
from ar_spec import verify, equivalent


OUT = ROOT / 'decoder-budget-replay'


def consume(session, history):
    if history.get('harness_forced'):
        assert session.pending_runs.pop(0) == history['body'][0]
        session.apply_action('run', history['body'])
    else:
        is_replan = 'Повторно разбери только русское условие' in history['prompt']
        if is_replan:
            assert session.pending_replan and not session.replan_attempted
            session.pending_replan = False; session.replan_attempted = True
        prompt = session.replan_request() if is_replan else session.request()
        assert prompt == history['prompt'], 'Replay prompt differs'
        value = history['generation']
        try:
            if is_replan:
                session.apply_replan(value['body'])
            else:
                session.apply_action(value['action'], value['body'])
        except (ValueError, ArithmeticError, RuntimeError) as error:
            session.observation = 'ERROR ' + str(error)
            session.history.append({'kind': 'error', 'observation': session.observation})
    assert session.history[-1]['kind'] == history['kind']
    session.history[-1] = copy.deepcopy(history)


def finish_record(old, session, goal, vm):
    session.finalize(); check = verify(vm, session.body, session.pool, goal['spec'], goal['audit_inputs'])
    correct = check['status'] == 'TESTED'; eligible = session.eligibility()[0]
    own = verify(vm, session.body, session.pool, session.declared_spec, goal['audit_inputs'])
    result = copy.deepcopy(old)
    result.update(body=session.body, program_correct=correct, spec_consistent=own['status'] == 'TESTED', finished=session.finished,
        eligible=eligible, **{'pass': bool(correct and session.finished and eligible)}, abstained=session.abstained,
        task_audit=check, declared_spec=session.declared_spec, gate_checks=session.gate_checks, history=session.history,
        rollback=session.rollback_performed, candidate_at_exit=session.candidate_at_exit,
        candidate_correct_at_exit=verify(vm, session.candidate_at_exit, session.pool, goal['spec'], goal['audit_inputs'])['status'] == 'TESTED',
        replans=session.replan_count, final_spec_intent=equivalent(session.declared_spec, goal['spec'], goal['audit_inputs']))
    claims = [h for h in session.history if h['kind'] in ['done', 'done_rejected']]
    result['DONE_claims'] = len(claims)
    result['false_DONE_claims'] = sum(verify(vm, h['evaluated_body'], session.pool, goal['spec'], goal['audit_inputs'])['status'] != 'TESTED' for h in claims)
    return result


def main(arm):
    check_frozen(); install()
    protocol = read(OUT / 'protocol.json')
    assert sha(__file__) == protocol['replay_driver_sha256']
    source = ROOT if (ROOT / 'export/fixed6000_full/model.mkqb').exists() else ROOT / 'server-results'
    original = read(source / ('fixed6000_' + arm) / 'closed.json')
    folder = source / 'export' / ('fixed6000_' + arm)
    model, receipt = verify_export(folder); model.cuda().eval().requires_grad_(False)
    tokenizer = AutoTokenizer.from_pretrained(folder / 'hf', local_files_only=True); compact_head(model, output_ids(tokenizer))
    goals = {g['id']: g for g in rows(ROOT / 'closed-clean.jsonl')}; vm = FullVM()
    merged = copy.deepcopy(original['self']['records']); repairs = []; changed = []; unaffected = 0
    for index, old in enumerate(original['self']['records']):
        error_index = next((i for i, h in enumerate(old['history']) if h['kind'] == 'generation_error'), None)
        if error_index is None:
            unaffected += 1; continue
        error = old['history'][error_index]; value = error['generation']
        if value.get('codec_error') != 'incomplete':
            unaffected += 1; continue
        old_tokens = value['generated_token_ids']; action = ACTIONS[ACTION_IDS.index(old_tokens[0])]
        own_budget = min(511, 1024 - value['input_tokens'] - len(header_ids(tokenizer, action)))
        actual_budget = len(old_tokens) - 1
        if actual_budget >= own_budget:
            unaffected += 1; continue
        goal = goals[old['task_id']]
        # An exhausted typed episode restores exactly its initial code.
        assert not old['finished'] and not old['abstained']
        session = Session(goal, old['body'], vm, 'spec', old['initial_spec'], True)
        for history in old['history'][:error_index]:
            consume(session, history)
        first = True
        for turn in range(len(session.history), MAX_TURNS):
            if session.finished or session.abstained or getattr(session, 'exhausted', False):
                break
            if session.pending_runs:
                case = session.pending_runs.pop(0); session.apply_action('run', [case]); session.history[-1]['harness_forced'] = 'missing_public_run'; continue
            replan = session.pending_replan and not session.replan_attempted
            if replan:
                session.pending_replan = False; session.replan_attempted = True
            prompt = session.replan_request() if replan else session.request()
            if first:
                assert prompt == error['prompt']
            generated = generate(model, tokenizer, [prompt], forced_action=action if first else ('write' if replan else None))[0]
            if first:
                assert generated['generated_token_ids'][:len(old_tokens)] == old_tokens, 'Prefix changed before old truncation'
                repairs.append({'id': old['id'], 'old_body_budget': actual_budget, 'own_body_budget': own_budget,
                    'prefix_identical': True, 'new_first_generation': generated, 'prompt': prompt,
                    'forced_action': action, 'previous_codec_error': 'incomplete'})
                first = False
            if generated.get('codec_error'):
                session.history.append({'kind': 'generation_error', 'prompt': prompt, 'generation': generated}); session.exhausted = True; continue
            try:
                if replan:
                    session.apply_replan(generated['body'])
                else:
                    session.apply_action(generated['action'], generated['body'])
            except (ValueError, ArithmeticError, RuntimeError) as failure:
                session.observation = 'ERROR ' + str(failure); session.history.append({'kind': 'error', 'observation': session.observation})
            session.history[-1].update(prompt=prompt, generation=generated)
        new = finish_record(old, session, goal, vm)
        merged[index] = new; changed.append({'id': old['id'], 'old_pass': old['pass'], 'new_pass': new['pass'],
            'new_false_DONE': new['finished'] and not new['program_correct']})
        print(json.dumps({'arm': arm, 'replayed': len(changed), 'id': old['id']}), flush=True)
    check_frozen()
    result = {'arm': arm, 'optimizer_updates': 0, 'posthoc_technical_correction_same_exam': True,
        'weights_unchanged': True, 'context_unchanged': 1024, 'action_budget_unchanged': 12,
        'original_summary': original['self']['summary'], 'corrected_summary': metrics(merged),
        'unaffected_episodes_retained': unaffected, 'affected_episodes_replayed': len(changed),
        'prefix_identity_checks': repairs, 'changes': changed, 'records': merged,
        'export_verification': receipt, 'source_closed_sha256': sha(source / ('fixed6000_' + arm) / 'closed.json'),
        'protocol_sha256': sha(OUT / 'protocol.json')}
    write(OUT / arm / 'results.json', result); write(OUT / arm / 'complete.json', {'complete': True, 'optimizer_updates': 0, 'unix': time.time()})
    print(json.dumps({k: v for k, v in result.items() if k not in ['records', 'changes', 'prefix_identity_checks']}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--arm', choices=['lora', 'full'], required=True); a = p.parse_args()
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False; main(a.arm)
