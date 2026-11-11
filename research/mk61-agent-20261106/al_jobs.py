"""Freeze crossed supervision, train internal adapters, and audit actual Q4."""
import argparse
import json
import math
import shutil
import time
import torch
from al_common import ROOT, HERE, PREVIOUS, PARENT, INITIAL, INITIAL_PACKET, ARMS, PANELS, ACTION_IDS, CORRECT_IDS, output_ids, compact_head, read, write, sha
from al_model import Agent, load
from al_eval import panel
from al_course import Course, loss, retention
from native_export import packet
from native_quant import attach, export


def evaluate(model, tokenizer, split):
    return {name: panel(model, tokenizer, read(ROOT/tasks.format(split=split)), read(ROOT/seeds.format(split=split)))[0] for name, tasks, seeds in PANELS}


def brief(report): return {n: {k: v for k, v in p.items() if k not in ['details', 'calibration', 'simple']} for n, p in report.items()}


def score(result, base):
    retained = all(p['passed'] >= base[n]['passed'] and p['false_DONE'] <= base[n]['false_DONE'] and
        p['correct_controls_completed'] >= base[n]['correct_controls_completed'] for n, p in result.items())
    utility = sum(w*(result[n]['passed']-4*result[n]['false_DONE'])/result[n]['total'] for n, w in [('main', .6), ('skills', .25), ('completion', .15)])
    return [retained, utility, -sum(p['false_DONE'] for p in result.values()), sum(p['passed'] for p in result.values())]


def prepare():
    data = json.loads((ROOT/'data-frozen.json').read_text())
    for n, d in data['files'].items(): assert sha(ROOT/n) == d, n
    assert sha(INITIAL/'model.safetensors') == data['source_master_sha256'] and sha(INITIAL_PACKET) == data['source_packet_sha256']
    protected = json.loads((PREVIOUS/'prepared.json').read_text())['source_hashes']
    for n, d in protected.items(): assert sha(HERE/n) == d, n
    tokenizer = None; counts = {}
    for arm in ARMS:
        model = Agent(arm, 'cpu'); tokenizer = model.tokenizer
        replica, _ = model.packed(ROOT/f'preflight-{arm}.mkqb')
        assert packet(ROOT/f'preflight-{arm}.mkqb')[1] == packet(INITIAL_PACKET)[1]
        counts[arm] = model.trainable_count(); del replica, model
    course = Course(tokenizer)
    assert all(not(set(r[0][0][:r[0][2]+1]) & set(ACTION_IDS+CORRECT_IDS)) for rows in course.rows.values() for r in rows)
    probe = Agent('late'); sample, _ = course.batch(0, 'cuda')
    with torch.nn.utils.parametrize.cached():
        value, _ = loss(probe, sample, torch.tensor(__import__('al_common').body_ids(tokenizer), device='cuda'), json.loads((ROOT/'policy.json').read_text()))
    value.backward()
    assert all(torch.isfinite(p.grad).all() for p in probe.parameters() if p.grad is not None)
    assert any(p.grad is not None and bool(p.grad.abs().sum()) for n, p in probe.named_parameters() if n.endswith('.0.B'))
    del probe; torch.cuda.empty_cache()
    names = sorted(set(protected) | {p.name for p in HERE.glob('al_*.py') if p.name not in ['al_remote.py', 'al_collect.py', 'al_verify.py', 'al_report.py', 'al_chat.py']})
    folder = ROOT/'training-source'; folder.mkdir(exist_ok=True)
    for n in names: shutil.copyfile(HERE/n, folder/n)
    write(ROOT/'prepared.json', {'source_hashes': {n: sha(HERE/n) for n in names},
        'files': {str(p.relative_to(ROOT)): sha(p) for p in folder.iterdir()}, 'trainable_parameters': counts,
        'fitting_crossed_groups': len(course.quads), 'fitting_rows': {n: len(v) for n, v in course.rows.items()},
        'source_Q4_payload_exact_both_arms': True, 'finite_nonzero_internal_gradients': True, 'preflight_optimizer_updates': 0})
    model, tokenizer = load(); base = evaluate(model, tokenizer, 'development'); write(ROOT/'initial-development.json', base)
    print(json.dumps({'preflight': 'passed', 'parameters': counts, 'quads': len(course.quads), 'baseline': brief(base)}), flush=True)


def train(arm):
    policy = json.loads((ROOT/'policy.json').read_text()); prepared = json.loads((ROOT/'prepared.json').read_text())
    for n, d in prepared['source_hashes'].items(): assert sha(HERE/n) == d, n
    out = ROOT/arm; out.mkdir(exist_ok=True); model = Agent(arm); original = model.input_digest()
    teacher, tokenizer = load(); teacher_digest = sha(INITIAL_PACKET); course = Course(tokenizer)
    base = json.loads((ROOT/'initial-development.json').read_text()); head = torch.tensor(__import__('al_common').body_ids(tokenizer), device='cuda')
    model.save_checkpoint(out/'best.safetensors'); write(out/'best.json', {'step': 0, 'key': score(base, base), 'sha256': sha(out/'best.safetensors')})
    adapters = [p for n, p in model.named_parameters() if p.requires_grad and n not in ['action_head', 'correct_head']]
    optimizer = torch.optim.AdamW([{'params': adapters, 'lr_base': policy['lr_lora'], 'weight_decay': .01},
        {'params': [model.action_head, model.correct_head], 'lr_base': policy['lr_heads'], 'weight_decay': 0.}])
    started = time.monotonic(); research = None; losses = []
    for step in range(1, policy['steps']+1):
        model.train(); optimizer.zero_grad(set_to_none=True)
        factor = min(1., step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups: group['lr'] = group['lr_base']*factor
        batch, anchors = course.batch(step, 'cuda')
        with torch.nn.utils.parametrize.cached(), torch.autocast('cuda', dtype=torch.bfloat16):
            value, parts = loss(model, batch, head, policy); keep, details = retention(model, teacher, anchors, head, policy)
            value = value+policy['distill_weight']*keep; parts.update(details)
        assert torch.isfinite(value); value.backward(); torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.); optimizer.step()
        losses.append(float(value.detach()))
        if step == 1 or step % 25 == 0:
            write(out/'status.json', {'phase': 'training', 'step': step, 'steps': policy['steps'],
                'loss': sum(losses[-25:])/len(losses[-25:]), 'components': parts, 'seconds': time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest() == original
            model.save_checkpoint(out/f'step-{step}.safetensors')
            replica, _ = model.packed(out/f'step-{step}.mkqb'); replica.cuda().eval(); compact_head(replica, output_ids(tokenizer))
            result = evaluate(replica, tokenizer, 'development'); key = score(result, base); write(out/f'development-{step}.json', result)
            best = json.loads((out/'best.json').read_text())
            if key > best['key']:
                model.save_checkpoint(out/'best.safetensors'); write(out/'best.json', {'step': step, 'key': key, 'sha256': sha(out/'best.safetensors')})
            if research is None or key[1:] > research['key'][1:]:
                model.save_checkpoint(out/'research.safetensors'); research = {'step': step, 'key': key, 'sha256': sha(out/'research.safetensors')}; write(out/'research.json', research)
            del replica; torch.cuda.empty_cache()
            print(json.dumps({'arm': arm, 'step': step, 'key': key, 'summary': brief(result)}), flush=True)
    assert model.input_digest() == original and all(p.grad is None for p in teacher.parameters()) and sha(INITIAL_PACKET) == teacher_digest
    model.save_checkpoint(out/'last.safetensors')
    write(out/'training.json', {'arm': arm, 'steps': policy['steps'], 'trainable_parameters': model.trainable_count(),
        'same_draw_digest': course.digest, 'counts': dict(course.counts), 'input_embedding_bit_identical': True,
        'teacher_frozen': True, 'seconds': time.monotonic()-started})
    write(out/'status.json', {'phase': 'trained', 'step': policy['steps']})


def export_profile(agent, folder, metadata):
    folder.mkdir(parents=True, exist_ok=True); model = agent.merged_master(); model.save_pretrained(folder/'hf', safe_serialization=True)
    agent.tokenizer.save_pretrained(folder/'hf'); attach(model, 'q4'); export(model, folder/'model.mkqb', 'q4')
    write(folder/'output-token-ids.json', output_ids(agent.tokenizer))
    write(folder/'protocol.json', json.loads((PARENT/'export/lr10-terminal/protocol.json').read_text()))
    write(folder/'manifest.json', {'arm': 'asm', 'parameter_count': 3022080, 'quantization_mode': 'q4', 'packed_sha256': sha(folder/'model.mkqb'),
        'checkpoint_files': {p.name: sha(p) for p in (folder/'hf').iterdir() if p.is_file()}, **metadata})


def audit(arm):
    assert (ROOT/'preselected.json').exists()
    for name in ['best', 'research']:
        model = Agent(arm, checkpoint=ROOT/arm/(name+'.safetensors'))
        replica, _ = model.packed(ROOT/arm/(name+'-audit.mkqb')); replica.cuda().eval(); compact_head(replica, output_ids(model.tokenizer))
        write(ROOT/arm/(name+'-fresh.json'), evaluate(replica, model.tokenizer, 'fresh'))
        export_profile(model, ROOT/'export'/(arm+('-research' if name == 'research' else '')), json.loads((ROOT/arm/(name+'.json')).read_text()))
        del model, replica; torch.cuda.empty_cache()
    write(ROOT/arm/'status.json', {'phase': 'complete'})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=['prepare', 'train', 'baseline', 'audit']); ap.add_argument('--arm', choices=ARMS); a = ap.parse_args()
    torch.set_num_threads(4); torch.manual_seed(141501); torch.backends.cuda.matmul.allow_tf32 = False
    if a.action == 'prepare': prepare()
    elif a.action == 'train': train(a.arm)
    elif a.action == 'audit': audit(a.arm)
    else:
        assert (ROOT/'preselected.json').exists(); model, tokenizer = load(); write(ROOT/'initial-fresh.json', evaluate(model, tokenizer, 'fresh'))
