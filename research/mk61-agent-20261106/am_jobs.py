"""Two-stage model/plan ablation, closed-form diagnostics, sealed Q4 exams."""
import argparse
import json
import math
import random
import shutil
import time
from pathlib import Path
import torch
from safetensors.torch import save_file
from am_common import ROOT, HERE, SOURCE, PARENT, INITIAL, INITIAL_PACKET, ARMS, OPS, BINDINGS, read, write, sha, body_ids, output_ids, compact_head
from am_model import Agent, load
from am_course import Course, loss, retention
from am_eval import evaluate, diagnostics, planning_diagnostics, features, make_plans
from al_jobs import score, brief
from native_export import packet
from native_quant import attach, export


def fit_probes(model, tokenizer):
    rng = random.Random(151401); rows = []
    for file in ['goals.jsonl','code-reading.jsonl']:
        values = [r for r in read(ROOT/file)if r['meaning'][0]>=0];rng.shuffle(values);rows += values[:2048]
    h = features(model,tokenizer,[r['prompt']for r in rows]).double()
    x = torch.cat([h,torch.ones((len(h),1),dtype=torch.double)],1); gram = x.T@x+torch.eye(129,dtype=torch.double)
    values = {}
    for name,index,classes in [('op_head',0,len(OPS)),('binding_head',1,BINDINGS)]:
        target = torch.nn.functional.one_hot(torch.tensor([r['meaning'][index]for r in rows]),classes).double()
        fitted = torch.linalg.solve(gram,x.T@target).float()*4
        values[name+'.weight'] = fitted[:-1].T.contiguous();values[name+'.bias'] = fitted[-1].contiguous()
    save_file(values,str(ROOT/'probe.safetensors'))
    return {'method':'ridge classifier on frozen source features','training_rows':len(rows),'ridge':1.,'logit_scale':4.,'optimizer_updates':0,
        'training_files_only':True,'probe_sha256':sha(ROOT/'probe.safetensors')}


def prepare():
    frozen = json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==frozen['source_master_sha256']and sha(INITIAL_PACKET)==frozen['source_packet_sha256']
    protected = json.loads((SOURCE/'prepared.json').read_text())['source_hashes']
    for n,d in protected.items():assert sha(HERE/n)==d,n
    model,tokenizer = load(); probe = fit_probes(model,tokenizer);del model;torch.cuda.empty_cache()
    agent = Agent('direct',probe=ROOT/'probe.safetensors'); course = Course(tokenizer,'direct')
    value,parts = loss(agent,course.batch(1,'cuda')[0],torch.tensor(body_ids(tokenizer),device='cuda'),json.loads((ROOT/'policy.json').read_text()));value.backward()
    assert all(torch.isfinite(p.grad).all()for p in agent.parameters()if p.grad is not None)
    assert any(p.grad is not None and bool(p.grad.abs().sum())for n,p in agent.named_parameters()if n.endswith('.0.B'))
    replica,_ = agent.packed(ROOT/'preflight.mkqb');assert packet(ROOT/'preflight.mkqb')[1]==packet(INITIAL_PACKET)[1]
    replica.cuda().eval();compact_head(replica,output_ids(tokenizer))
    baseline_meaning = diagnostics(replica,tokenizer,'development',agent)
    baseline_planning = planning_diagnostics(replica,tokenizer,'development')
    write(ROOT/'initial-meaning.json',baseline_meaning);write(ROOT/'initial-planning.json',baseline_planning)
    base = evaluate(replica,tokenizer,'development','legacy');write(ROOT/'initial-development.json',base)
    names = sorted(set(protected)|{p.name for p in HERE.glob('am_*.py')if p.name not in ['am_remote.py','am_collect.py','am_verify.py','am_report.py','am_chat.py','am_native.py']})
    folder = ROOT/'training-source';folder.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,folder/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in folder.iterdir()},
        'probe':probe,'trainable_parameters':agent.trainable_count(),'auxiliary_parameters':sum(p.numel()for n,p in agent.named_parameters()if n.startswith(('op_head.','binding_head.','error_head.'))),
        'deployed_parameter_count':sum(p.numel()for p in replica.parameters()),'input_embedding_sha256':agent.input_digest(),
        'source_Q4_payload_exact':True,'finite_internal_and_auxiliary_gradients':True,'preflight_optimizer_updates':0})
    print(json.dumps({'preflight':'passed','probe':baseline_meaning,'goal_plan_correct':baseline_planning['passed'],'goal_plan_total':baseline_planning['total'],
        'baseline':brief(base),'trainable':agent.trainable_count()}),flush=True)


def train(arm):
    policy = json.loads((ROOT/'policy.json').read_text());prepared = json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    assert sha(ROOT/'probe.safetensors')==prepared['probe']['probe_sha256']
    out = ROOT/arm;out.mkdir(exist_ok=True);model = Agent(arm,probe=ROOT/'probe.safetensors');original = model.input_digest()
    teacher,tokenizer = load();course = Course(tokenizer,arm);head = torch.tensor(body_ids(tokenizer),device='cuda')
    base = json.loads((ROOT/'initial-development.json').read_text()); model.save_checkpoint(out/'best.safetensors')
    write(out/'best.json',{'step':0,'key':score(base,base),'sha256':sha(out/'best.safetensors'),'runtime_mode':'legacy'})
    adapters = [p for n,p in model.named_parameters()if p.requires_grad and n not in ['action_head','correct_head']and not n.startswith(('op_head.','binding_head.','error_head.'))]
    aux = list(model.op_head.parameters())+list(model.binding_head.parameters())+list(model.error_head.parameters())
    optimizer = torch.optim.AdamW([{'params':adapters,'lr_base':policy['lr_lora'],'weight_decay':.01},
        {'params':[model.action_head,model.correct_head],'lr_base':policy['lr_heads'],'weight_decay':0.},
        {'params':aux,'lr_base':policy['lr_aux'],'weight_decay':0.}])
    started = time.monotonic();research = None;losses = []; common_sha = None
    for step in range(1,policy['steps']+1):
        model.train();optimizer.zero_grad(set_to_none=True)
        factor = min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr'] = group['lr_base']*factor
        batch,anchors = course.batch(step,'cuda')
        with torch.nn.utils.parametrize.cached(),torch.autocast('cuda',dtype=torch.bfloat16):
            value,parts = loss(model,batch,head,policy);keep,details = retention(model,teacher,anchors,head,policy)
            value += policy['distill_weight']*keep;parts.update(details)
        assert torch.isfinite(value);value.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step()
        losses.append(float(value.detach()))
        if step==1 or step%25==0:
            write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],'stage':1 if step<=250 else 2,
                'loss':sum(losses[-25:])/len(losses[-25:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==original;model.save_checkpoint(out/f'step-{step}.safetensors')
            if step==250:common_sha = sha(out/f'step-{step}.safetensors')
            replica,_ = model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(tokenizer))
            result = evaluate(replica,tokenizer,'development',arm);key_score = score(result,base);write(out/f'development-{step}.json',result)
            write(out/f'meaning-{step}.json',diagnostics(replica,tokenizer,'development',model))
            write(out/f'planning-{step}.json',planning_diagnostics(replica,tokenizer,'development'))
            best = json.loads((out/'best.json').read_text())
            if key_score>best['key']:
                model.save_checkpoint(out/'best.safetensors');write(out/'best.json',{'step':step,'key':key_score,'sha256':sha(out/'best.safetensors'),'runtime_mode':arm})
            if research is None or key_score[1:]>research['key'][1:]:
                model.save_checkpoint(out/'research.safetensors');research={'step':step,'key':key_score,'sha256':sha(out/'research.safetensors'),'runtime_mode':arm};write(out/'research.json',research)
            if step in policy['plan_cache_updates']:
                course.plans = make_plans(replica,tokenizer,read(ROOT/'goals.jsonl'))
                write(out/f'self-plans-{step}.json',course.plans)
            del replica;torch.cuda.empty_cache()
            print(json.dumps({'arm':arm,'step':step,'key':key_score,'summary':brief(result)}),flush=True)
    assert model.input_digest()==original and all(p.grad is None for p in teacher.parameters())
    model.save_checkpoint(out/'last.safetensors')
    write(out/'training.json',{'steps':policy['steps'],'same_draw_digest':course.digest,'counts':dict(course.counts),
        'stage1_checkpoint_sha256':common_sha,'trainable_parameters':model.trainable_count(),'input_rows_unchanged':True,
        'teacher_frozen':True,'seconds':time.monotonic()-started,'auxiliary_heads_not_exported':True})
    write(out/'status.json',{'phase':'trained','step':policy['steps']})


def export_profile(agent,folder,metadata):
    folder.mkdir(parents=True,exist_ok=True);model = agent.merged_master();assert sum(p.numel()for p in model.parameters())==3022080
    model.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf');attach(model,'q4');export(model,folder/'model.mkqb','q4')
    write(folder/'output-token-ids.json',output_ids(agent.tokenizer));shutil.copyfile(PARENT/'export/lr10-terminal/protocol.json',folder/'protocol.json')
    write(folder/'manifest.json',{'arm':'asm','parameter_count':3022080,'quantization_mode':'q4','packed_sha256':sha(folder/'model.mkqb'),
        'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'auxiliary_heads_dropped':True,**metadata})


def audit(arm):
    assert(ROOT/'preselected.json').exists()
    for role in ['best','research']:
        metadata = json.loads((ROOT/arm/(role+'.json')).read_text());model = Agent(arm,checkpoint=ROOT/arm/(role+'.safetensors'))
        replica,_ = model.packed(ROOT/arm/(role+'-audit.mkqb'));replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
        write(ROOT/arm/(role+'-fresh.json'),evaluate(replica,model.tokenizer,'fresh',metadata['runtime_mode']))
        write(ROOT/arm/(role+'-meaning-fresh.json'),diagnostics(replica,model.tokenizer,'fresh',model))
        write(ROOT/arm/(role+'-planning-fresh.json'),planning_diagnostics(replica,model.tokenizer,'fresh'))
        export_profile(model,ROOT/'export'/(arm+('-research'if role=='research'else'')),metadata)
        del model,replica;torch.cuda.empty_cache()
    write(ROOT/arm/'status.json',{'phase':'complete'})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','train','baseline','audit']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(151501);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    elif a.action=='audit':audit(a.arm)
    else:
        assert(ROOT/'preselected.json').exists();model,tokenizer=load();write(ROOT/'initial-fresh.json',evaluate(model,tokenizer,'fresh','legacy'))
        probe = Agent('direct',probe=ROOT/'probe.safetensors');write(ROOT/'initial-meaning-fresh.json',diagnostics(model,tokenizer,'fresh',probe));write(ROOT/'initial-planning-fresh.json',planning_diagnostics(model,tokenizer,'fresh'))
