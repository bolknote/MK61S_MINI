"""Raw tool episodes; self-hypothesis and hidden grading are kept separate."""
import collections
import copy
import json
import torch
import torch.nn.functional as F
from al_eval import generate, panel as legacy_panel
from am_common import ROOT, PANELS, read, labels
from am_runtime import goal_prompt, code_prompt, key, snapshot, bounded_render, execute_hypothesis
from am_data import safe_view
from aj_teacher import make_session, correct
from ac_eval import stats
from ac_protocol import prompt_ids
from full_isa_vm import FullVM
from ha_protocol import encode


def make_plans(model, tokenizer, goals):
    result = {}; vm = FullVM(); values = list(goals)
    for at in range(0, len(values), 24):
        group = values[at:at+24]; texts = [goal_prompt(g['view'], g['pool']) for g in group]
        generated = generate(model, tokenizer, texts, forced_action='write')
        for g, p, text in zip(group, generated, texts):
            result[g['key']] = execute_hypothesis(g['view'], g['pool'], p, vm)
            result[g['key']]['prompt'] = text
    return result


def panel(model, tokenizer, tasks, seeds, arm):
    lookup = {t['id']: t for t in tasks}; vm = FullVM(); records = []; cache = {}
    for at in range(0, len(seeds), 24):
        items = seeds[at:at+24]; sessions = [make_session(lookup[s['task_id']], s, vm) for s in items]
        goals = []; keys = []
        for s in sessions:
            view = safe_view(s.task, s.pool); k = key(view, s.pool); keys.append(k)
            if arm == 'planned' and k not in cache: goals.append({'key': k, 'view': view, 'pool': s.pool})
        if goals: cache.update(make_plans(model, tokenizer, {g['key']: g for g in goals}.values()))
        for s, k in zip(sessions, keys):
            s.gate = False; s.exhausted = getattr(s, 'exhausted', False)
            s.planning = cache.get(k)
        for turn in range(10):
            active = [s for s in sessions if not s.finished and not s.abstained and not s.exhausted and len(s.history)-s.initial_history < 10]
            if not active: break
            prompts = [bounded_render(tokenizer, snapshot(s), s.planning) for s in active]
            generated = generate(model, tokenizer, prompts)
            for s, p, g in zip(active, prompts, generated):
                if g.get('codec_error'):
                    s.history.append({'kind': 'generation_error', 'prompt': p, 'generation': g}); s.exhausted = True; continue
                s.apply_action(g['action'], g['body']); s.history[-1].update(prompt=p, generation=g)
        for seed, s in zip(items, sessions):
            t = lookup[seed['task_id']]; ok = correct(vm, t, s.body, s.pool); eligible = s.eligibility()[0]
            r = {'id': t['id'], 'level': t.get('level', 1), 'initially_correct': seed['intentionally_correct'],
                'program_correct': ok, 'finished': s.finished, 'eligible': eligible, 'pass': ok and s.finished and eligible,
                'abstained': s.abstained, 'body': s.body, 'history': s.history}
            if s.planning is not None:
                r['planning'] = {'prompt': s.planning['prompt'], 'generation': s.planning['generation'],
                    'program_correct_offline_only': correct(vm,t,s.planning['body'],s.pool), 'error':s.planning.get('error')}
            records.append(r)
    return {**stats(records), 'details': records, 'runtime_mode': arm, 'reference_in_runtime': False,
        'runtime_planning_calls': len(cache), 'external_semantic_veto': False}


def evaluate(model, tokenizer, split, arm):
    return {name: (legacy_panel(model,tokenizer,read(ROOT/tf.format(split=split)),read(ROOT/sf.format(split=split)))[0]
        if arm == 'legacy' else panel(model,tokenizer,read(ROOT/tf.format(split=split)),read(ROOT/sf.format(split=split)),arm))
        for name, tf, sf in PANELS}


def features(model, tokenizer, prompts):
    parts = []
    for at in range(0, len(prompts), 32):
        encoded = [prompt_ids(tokenizer,p) for p in prompts[at:at+32]]
        assert all(len(x) < 1016 for x in encoded)
        width = max(map(len,encoded)); device = next(model.parameters()).device
        ids = torch.zeros((len(encoded),width),dtype=torch.long,device=device); mask = torch.zeros_like(ids)
        for i,x in enumerate(encoded):ids[i,:len(x)] = torch.tensor(x,device=device);mask[i,:len(x)] = 1
        with torch.inference_mode():
            h = model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            parts.append(h[torch.arange(len(ids),device=device),mask.sum(1)-1].float().cpu())
    return torch.cat(parts)


def meaning_examples(split):
    rows = []
    for t in read(ROOT/(split+'-skills.jsonl')):
        pool = t['constants']; view = safe_view(t,pool); target = labels(t,pool)
        rows += [{'kind':'goal','prompt':goal_prompt(view,pool),'labels':target},
            {'kind':'code','prompt':code_prompt(view,pool,encode(t['reference_code'],pool,'asm')),'labels':target}]
    return rows


def diagnostics(model, tokenizer, split, heads):
    rows = meaning_examples(split); h = features(model,tokenizer,[r['prompt']for r in rows]); out = {}
    with torch.no_grad():
        op = F.linear(h,heads.op_head.weight.detach().cpu(),heads.op_head.bias.detach().cpu()).argmax(-1)
        binding = F.linear(h,heads.binding_head.weight.detach().cpu(),heads.binding_head.bias.detach().cpu()).argmax(-1)
    for kind in ['goal','code']:
        ids = [i for i,r in enumerate(rows)if r['kind']==kind]
        out[kind] = {'total':len(ids),'operation':sum(int(op[i])==rows[i]['labels'][0]for i in ids),
            'argument':sum(int(binding[i])==rows[i]['labels'][1]for i in ids),
            'both':sum(int(op[i])==rows[i]['labels'][0]and int(binding[i])==rows[i]['labels'][1]for i in ids)}
    return out


def planning_diagnostics(model, tokenizer, split):
    tasks = read(ROOT/(split+'.jsonl'))+read(ROOT/(split+'-skills.jsonl')); vm = FullVM(); rows = []
    for at in range(0,len(tasks),24):
        group = tasks[at:at+24]; texts = [goal_prompt(safe_view(t,t['constants']),t['constants'])for t in group]
        for t,p,g in zip(group,texts,generate(model,tokenizer,texts,forced_action='write')):
            rows.append({'id':t['id'],'prompt':p,'generation':g,'pass':not g.get('codec_error')and correct(vm,t,g['body'],t['constants']),
                'group':t['group']})
    return {'total':len(rows),'passed':sum(r['pass']for r in rows),'details':rows}
