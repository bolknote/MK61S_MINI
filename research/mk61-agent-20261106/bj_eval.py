"""Fresh frozen exam: synthesis, typed recovery, claims, preservation and coverage."""
import copy
from bj_common import ROOT, rows, read, MAX_TURNS
from bh_spec import install
import bh_eval
import ay_eval as core
from aq_eval import generate
from bj_runtime import Session, SPEC_DIAG, render
from ar_spec import verify, infer, equivalent
from full_isa_vm import FullVM


def episodes(model, tokenizer, goals, plans, vm, gate):
    jobs = []
    for i, g in enumerate(goals):
        kind, bad = core.mutant(g, vm, ['operation', 'argument', 'order'][i % 3])
        jobs += [(g, 'correct', g['reference_body']), (g, kind, bad)]
    records = []
    for at in range(0, len(jobs), 24):
        chunk = jobs[at:at + 24]
        sessions = [Session(g, body, vm, 'spec', plans[g['id']]['declared_spec'], gate == 'self') for g, _, body in chunk]
        for turn in range(MAX_TURNS):
            active = [s for s in sessions if not s.finished and not s.abstained and not getattr(s, 'exhausted', False)]
            if not active:
                break
            normal = []; replan = []
            for s in active:
                if s.pending_runs:
                    case = s.pending_runs.pop(0)
                    s.apply_action('run', [case])
                    s.history[-1]['harness_forced'] = 'missing_public_run'
                elif s.pending_replan and not s.replan_attempted:
                    s.pending_replan = False; s.replan_attempted = True; replan.append(s)
                else:
                    normal.append(s)
            for values, is_replan in [(normal, False), (replan, True)]:
                if not values:
                    continue
                prompts = [s.replan_request() if is_replan else s.request() for s in values]
                output = generate(model, tokenizer, prompts, forced_action='write' if is_replan else None)
                for s, prompt, generation in zip(values, prompts, output):
                    if generation.get('codec_error'):
                        s.history.append({'kind': 'generation_error', 'prompt': prompt, 'generation': generation})
                        s.exhausted = True; continue
                    try:
                        if is_replan:
                            s.apply_replan(generation['body'])
                        else:
                            s.apply_action(generation['action'], generation['body'])
                    except (ValueError, ArithmeticError, RuntimeError) as error:
                        s.observation = 'ERROR ' + str(error)
                        s.history.append({'kind': 'error', 'observation': s.observation})
                    s.history[-1].update(prompt=prompt, generation=generation)
        for (g, label, initial), s in zip(chunk, sessions):
            s.finalize()
            check = verify(vm, s.body, s.pool, g['spec'], g['audit_inputs'])
            correct = check['status'] == 'TESTED'; eligible = s.eligibility()[0]
            own = verify(vm, s.body, s.pool, s.declared_spec, g['audit_inputs'])
            false_claims = 0; claims = 0
            for h in s.history:
                if h['kind'] in ['done', 'done_rejected']:
                    claims += 1
                    false_claims += verify(vm, h['evaluated_body'], s.pool, g['spec'], g['audit_inputs'])['status'] != 'TESTED'
            records.append({'id': g['id'] + ':' + label, 'task_id': g['id'], 'panel': g['panel'], 'family': g['family'],
                'initial': label, 'initially_correct': label == 'correct', 'gate': gate,
                'program_correct': correct, 'spec_consistent': own['status'] == 'TESTED', 'finished': s.finished,
                'eligible': eligible, 'pass': bool(correct and s.finished and eligible), 'abstained': s.abstained,
                'body': s.body, 'task_audit': check, 'declared_spec': s.declared_spec, 'initial_spec': s.initial_spec,
                'gate_checks': s.gate_checks, 'history': s.history, 'rollback': s.rollback_performed,
                'candidate_at_exit': s.candidate_at_exit, 'candidate_correct_at_exit': verify(vm, s.candidate_at_exit, s.pool, g['spec'], g['audit_inputs'])['status'] == 'TESTED',
                'DONE_claims': claims, 'false_DONE_claims': false_claims, 'replans': s.replan_count,
                'final_spec_intent': equivalent(s.declared_spec, g['spec'], g['audit_inputs'])})
    return records


def metrics(records):
    result = core.episode_metrics(records)
    result.update(episodes_with_false_DONE_claims=sum(r['false_DONE_claims'] > 0 for r in records),
                  all_DONE_claims=sum(r['DONE_claims'] for r in records), false_DONE_claims=sum(r['false_DONE_claims'] for r in records),
                  rollbacks=sum(r['rollback'] for r in records), replans=sum(r['replans'] for r in records),
                  uncommitted_correct_candidates=sum(r['rollback'] and r['candidate_correct_at_exit'] for r in records))
    return result


def discrimination(model, tokenizer, goals, vm):
    prompts = []; labels = []
    for i, g in enumerate(goals):
        _, bad = core.mutant(g, vm, ['operation', 'argument', 'order'][i % 3])
        try:
            bad_spec = infer(bad, g['pool'], g['spec']['angle'])
            if equivalent(bad_spec, g['spec'], g['audit_inputs'])['tested_equal']:
                continue
        except (ValueError, ArithmeticError):
            continue
        for spec_ok, code_ok in [(True, True), (True, False), (False, True), (False, False)]:
            s = Session(g, g['reference_body'] if code_ok else bad, vm, 'spec', g['spec'] if spec_ok else bad_spec, True)
            prompts.append(s.request()); labels.append({'task_id': g['id'], 'spec_ok': spec_ok, 'code_ok': code_ok,
                'expected_action': ('done' if code_ok else 'write') if spec_ok else 'diag'})
    records = []
    for at in range(0, len(prompts), 24):
        for p, expected, generated in zip(prompts[at:at + 24], labels[at:at + 24], generate(model, tokenizer, prompts[at:at + 24])):
            correct = generated.get('action') == expected['expected_action']
            if not expected['spec_ok']:
                correct = correct and generated.get('body') == SPEC_DIAG
            records.append({**expected, 'correct': correct, 'generation': generated, 'prompt': p})
    return {'total': len(records), 'correct': sum(r['correct'] for r in records), 'records': records,
            'bad_spec': {'total': sum(not r['spec_ok'] for r in records), 'detected': sum(not r['spec_ok'] and r['correct'] for r in records)}}


def evaluate(model, tokenizer, split):
    install()
    if split == 'closed':
        assert (ROOT / 'preselected.json').exists()
    goals = rows(ROOT / (split + '-clean.jsonl')); vm = FullVM()
    primary = core.primary(model, tokenizer, goals, 'spec', vm)
    natural = [r for r in primary if r['panel'] != 'structured']
    result = {'split': split, 'primary': {'summary': core.primary_metrics(primary), 'natural': core.primary_metrics(natural),
              'panels': {p: core.primary_metrics([r for r in primary if r['panel'] == p]) for p in ['known', 'novel', 'editorial', 'structured']}, 'records': primary}}
    cohort = core.choose_runtime(goals, 96 if split == 'development' else 256, 261111117)
    plans = {r['id']: r for r in primary}
    for gate in ['raw', 'self']:
        values = episodes(model, tokenizer, cohort, plans, vm, gate)
        result[gate] = {'summary': metrics(values), 'records': values}
    values = core.episodes(model, tokenizer, cohort, 'spec', plans, vm, 'self')
    initial_bodies = {}
    goal_by_id = {g['id']: g for g in cohort}
    for i, g in enumerate(cohort):
        kind, bad = core.mutant(g, vm, ['operation', 'argument', 'order'][i % 3])
        initial_bodies[g['id'] + ':correct'] = g['reference_body']
        initial_bodies[g['id'] + ':' + kind] = bad
    for row in values:
        current = initial_bodies[row['id']]; g = goal_by_id[row['task_id']]
        row['DONE_claims'] = 0; row['false_DONE_claims'] = 0
        for h in row['history']:
            if h['kind'] == 'write':
                current = h['body']
            if h['kind'] in ['done', 'done_rejected']:
                row['DONE_claims'] += 1
                row['false_DONE_claims'] += verify(vm, current, g['pool'], g['spec'], g['audit_inputs'])['status'] != 'TESTED'
    legacy_summary = core.episode_metrics(values)
    legacy_summary.update(episodes_with_false_DONE_claims=sum(r['false_DONE_claims'] > 0 for r in values),
                          all_DONE_claims=sum(r['DONE_claims'] for r in values), false_DONE_claims=sum(r['false_DONE_claims'] for r in values))
    result['legacy_self'] = {'summary': legacy_summary, 'records': values}
    result['discrimination'] = discrimination(model, tokenizer, core.choose_runtime(goals, 24 if split == 'development' else 64, 261111118), vm)
    return result


def key(report, parent):
    protected = True
    for gate in ['raw', 'self']:
        a = report[gate]['summary']; b = parent[gate]['summary']
        protected &= a['false_DONE'] <= b['false_DONE'] and a['correct_starts_corrupted'] <= b['correct_starts_corrupted'] and a['wrong_starts_repaired'] >= b['wrong_starts_repaired'] and a['passed'] >= b['passed']
        protected &= a['episodes_with_false_DONE_claims'] <= b['episodes_with_false_DONE_claims']
    a = report['self']['summary']; b = parent['legacy_self']['summary']
    protected &= a['false_DONE'] <= b['false_DONE'] and a['correct_starts_corrupted'] <= b['correct_starts_corrupted'] and a['wrong_starts_repaired'] >= b['wrong_starts_repaired'] and a['passed'] >= b['passed']
    protected &= a['episodes_with_false_DONE_claims'] <= b['episodes_with_false_DONE_claims']
    rate = lambda p: p['passed'] / p['total']
    for panel in ['editorial', 'structured']:
        protected &= rate(report['primary']['panels'][panel]) >= rate(parent['primary']['panels'][panel]) - .05
    protected &= rate(report['primary']['natural']) >= rate(parent['primary']['natural']) - .03
    return [bool(protected), report['self']['summary']['wrong_starts_repaired'], report['self']['summary']['passed'],
            -report['self']['summary']['false_DONE'], -report['self']['summary']['correct_starts_corrupted'], rate(report['primary']['natural'])]


def brief(report):
    return {'natural': report['primary']['natural'], 'panels': report['primary']['panels'],
            **{k: report[k]['summary'] for k in ['raw', 'self', 'legacy_self']},
            'discrimination': {k: v for k, v in report['discrimination'].items() if k != 'records'}}
