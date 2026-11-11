"""Development-only folding of the learned correctness signal into DONE."""
import argparse
import json
import math
import shutil
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM, AutoTokenizer
from al_common import ROOT, ARMS, PANELS, ACTIONS, ACTION_IDS, CORRECT_IDS, read, write, sha, compact_head, output_ids
from al_jobs import evaluate, score, brief
from aj_teacher import make_session, row
from ac_protocol import prompt_ids
from full_isa_vm import FullVM
from af_model import aligned_q4
from lowbit import load
from native_quant import attach, export


def model_for(folder):
    model = AutoModelForCausalLM.from_pretrained(folder/'hf', local_files_only=True)
    load(model, folder/'model.mkqb'); model.requires_grad_(False); model.cuda().eval()
    tokenizer = AutoTokenizer.from_pretrained(folder/'hf', local_files_only=True)
    compact_head(model, output_ids(tokenizer)); return model, tokenizer


def control(arm):
    assert (ROOT/'complete.json').exists()
    metadata = json.loads((ROOT/arm/'research.json').read_text()); step = metadata['step']
    dev = json.loads((ROOT/arm/f'development-{step}.json').read_text()); base = json.loads((ROOT/'initial-development.json').read_text())
    model, tokenizer = model_for(ROOT/'export'/(arm+'-research')); vm = FullVM(); states = {}
    for name, tf, sf in PANELS:
        tasks = {t['id']: t for t in read(ROOT/tf.format(split='development'))}
        for seed, episode in zip(read(ROOT/sf.format(split='development')), dev[name]['details']):
            t = tasks[seed['task_id']]; s = make_session(t, seed, vm)
            for h in episode['history']:
                if 'prompt' not in h or 'generation' not in h: continue
                assert s.request() == h['prompt']
                r = row(s, t, 'coupling_development_only'); states[r['prompt']] = r
                g = h['generation']
                if g.get('codec_error'): break
                s.apply_action(g['action'], g['body'])
                if s.finished or s.abstained: break
    features = []; ready = []
    rows = list(states.values())
    for at in range(0, len(rows), 32):
        chunk = rows[at:at+32]; enc = [prompt_ids(tokenizer, r['prompt']) for r in chunk]
        keep = [i for i, p in enumerate(enc) if len(p) < 1016]
        if not keep: continue
        width = max(len(enc[i]) for i in keep); ids = torch.zeros((len(keep), width), dtype=torch.long, device='cuda'); mask = torch.zeros_like(ids)
        for j, i in enumerate(keep): ids[j, :len(enc[i])] = torch.tensor(enc[i], device='cuda'); mask[j, :len(enc[i])] = 1
        with torch.inference_mode():
            h = model.model(input_ids=ids, attention_mask=mask, use_cache=False).last_hidden_state
            features.append(h[torch.arange(len(ids), device='cuda'), mask.sum(1)-1].float())
        ready += [bool(chunk[i]['correctness'] and chunk[i]['eligible_for_DONE'] and chunk[i]['action'] == 'done') for i in keep]
    h = torch.cat(features); ready = torch.tensor(ready, device='cuda', dtype=torch.bool)
    weight = model.get_input_embeddings().weight; original = weight[ACTION_IDS].detach().clone()
    direction = (weight[CORRECT_IDS[1]]-weight[CORRECT_IDS[0]]).detach().clone(); done = ACTIONS.index('done')
    def heads(beta):
        value = original.clone(); value[done] += beta*direction; return aligned_q4(value)
    initial = F.linear(h, original).argmax(-1); curve = []
    for beta in [0., .025, .05, .1, .15, .25, .4, .65, 1.]:
        pred = F.linear(h, heads(beta)).argmax(-1)
        curve.append({'beta': beta, 'false_DONE': int(((pred == done)&~ready).sum()),
            'lost_correct_DONE': int(((initial == done)&ready&(pred != done)).sum()),
            'correct_DONE': int(((pred == done)&ready).sum())})
    limit = max(1, math.floor(int(((initial == done)&ready).sum())*.02))
    ranked = sorted([v for v in curve if v['beta'] > 0 and v['lost_correct_DONE'] <= limit],
        key=lambda v: (v['false_DONE'], v['lost_correct_DONE'], -v['correct_DONE']))
    candidates = []; weights = []
    for v in ranked:
        w = heads(v['beta'])
        if torch.equal(w, original) or any(torch.equal(w, old) for old in weights): continue
        candidates.append(v['beta']); weights.append(w)
        if len(candidates) == 2: break
    write(ROOT/arm/'coupling-plan.json', {'curve': curve, 'candidates': candidates, 'source_step': step,
        'fresh_results_not_inspected': True, 'development_only': True})
    best = {'source_fallback': True, 'step': 0, 'beta': 0., 'key': score(base, base)}; records = []
    for beta in candidates:
        with torch.no_grad(): weight[ACTION_IDS] = heads(beta)
        report = evaluate(model, tokenizer, 'development'); key = score(report, base)
        records.append({'beta': beta, 'key': key, 'summary': brief(report)})
        if key > best['key']:
            best = {'source_fallback': False, 'step': step, 'beta': beta, 'key': key}
    write(ROOT/arm/'coupling-development.json', records); write(ROOT/arm/'coupled.json', best)
    print(json.dumps({'arm': arm, 'selected_coupling': best, 'candidates': candidates}), flush=True)


def audit(arm):
    assert (ROOT/'coupling-preselected.json').exists()
    choice = json.loads((ROOT/arm/'coupled.json').read_text()); out = ROOT/'export'/(arm+'-coupled')
    if choice['source_fallback']:
        assert json.loads((ROOT/arm/'best.json').read_text())['step'] == 0
        shutil.copytree(ROOT/'export'/arm, out, dirs_exist_ok=True)
        shutil.copyfile(ROOT/arm/'best-fresh.json', ROOT/arm/'coupled-fresh.json')
        write(out/'coupling.json', choice); return
    model, tokenizer = model_for(ROOT/'export'/(arm+'-research')); weight = model.get_input_embeddings().weight
    with torch.no_grad():
        weight[ACTION_IDS[3]] = aligned_q4((weight[ACTION_IDS[3]]+choice['beta']*(weight[CORRECT_IDS[1]]-weight[CORRECT_IDS[0]])).reshape(1, -1))[0]
    write(ROOT/arm/'coupled-fresh.json', evaluate(model, tokenizer, 'fresh'))
    out.mkdir(parents=True, exist_ok=True); model.cpu(); model.save_pretrained(out/'hf', safe_serialization=True); tokenizer.save_pretrained(out/'hf')
    attach(model, 'q4'); export(model, out/'model.mkqb', 'q4')
    for name in ['protocol.json', 'output-token-ids.json']: shutil.copyfile(ROOT/'export'/(arm+'-research')/name, out/name)
    write(out/'manifest.json', {'arm': 'asm', 'quantization_mode': 'q4', 'packed_sha256': sha(out/'model.mkqb'),
        'checkpoint_files': {p.name: sha(p) for p in (out/'hf').iterdir() if p.is_file()}, 'parameter_count': 3022080, **choice})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['control', 'audit']); ap.add_argument('--arm', choices=ARMS, required=True); a = ap.parse_args()
    torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False
    (control if a.action == 'control' else audit)(a.arm)
