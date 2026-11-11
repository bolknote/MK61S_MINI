"""Corrected second phase: one actual common checkpoint and legacy actor text."""
import argparse
import copy
import json
import math
import random
import shutil
import time
import torch
from an_common import ROOT,WARMUP,COMMON_CHECKPOINT,HERE,PARENT,INITIAL,INITIAL_PACKET,ARMS,read,write,sha,body_ids,output_ids,compact_head
from am_model import Agent,load
from an_course import Course,loss,retention
from an_eval import evaluate,diagnostics,planning_diagnostics,make_plans
from am_jobs import export_profile
from al_jobs import score,brief
from an_runtime import render
from native_export import packet


def prepare():
    ROOT.mkdir(exist_ok=True);old=json.loads((WARMUP/'data-frozen.json').read_text());warm=json.loads((WARMUP/'prepared.json').read_text())
    cutover=json.loads((WARMUP/'stage2-cutover.json').read_text())
    assert cutover['fresh_results_not_inspected']and sha(COMMON_CHECKPOINT)==cutover['common_checkpoint_sha256']
    for n,d in old['files'].items():
        assert sha(WARMUP/n)==d,n
        if n!='policy.json':shutil.copyfile(WARMUP/n,ROOT/n)
    policy=json.loads((WARMUP/'policy.json').read_text());policy.update(steps=500,checkpoints=[250,500],plan_cache_updates=[250],
        actor_state_format='legacy exact',train_plan_cache_goals=1024,both_arms_start_one_checkpoint=True,optimizer_reset_both=True)
    write(ROOT/'policy.json',policy);shutil.copyfile(WARMUP/'probe.safetensors',ROOT/'probe.safetensors')
    shutil.copyfile(COMMON_CHECKPOINT,ROOT/'common.safetensors');shutil.copytree(WARMUP/'core-source',ROOT/'core-source',dirs_exist_ok=True)
    for n in ['initial-development.json','initial-meaning.json','initial-planning.json']:shutil.copyfile(WARMUP/n,ROOT/n)
    write(ROOT/'warmup-data-frozen.json',old);write(ROOT/'stage2-cutover.json',cutover)
    files={p.name:sha(p)for p in ROOT.iterdir()if p.suffix in ['.json','.jsonl','.safetensors']and p.name not in ['data-frozen.json','prepared.json','status.json','start-launch.json']}
    write(ROOT/'data-frozen.json',{**{k:v for k,v in old.items()if k!='files'},'files':files,
        'same_development_and_fresh_as_uninspected_v1':True,'common_checkpoint_sha256':sha(COMMON_CHECKPOINT),
        'common_stage_updates':250,'duplicate_warmup_computed':250,'continuation_updates_per_arm':500,
        'superseded_original_optimizer_updates_lower_bound':sum(r['step']for r in cutover['last_status'].values())})
    for n,d in warm['source_hashes'].items():assert sha(HERE/n)==d,n
    # Verify the restored text against the existing Session implementation.
    from ac_runtime import Session
    rows=read(ROOT/'tool-lessons.jsonl');checked=0
    for r in rows[::max(1,len(rows)//128)]:
        state=r['state'];s=object.__new__(Session);s.task=state['view'];s.arm='asm';s.pool=state['pool'];s.body=state['body']or None
        s.case=state['case'];s.revision=state['revision'];s.runs={int(k):v for k,v in state['runs'].items()};s.observation=state['observation'];s.max_turns=10
        s.initial_history=0;s.history=[None]*(10-state['remaining']);assert s.request()==render(state);checked+=1
    model=Agent('direct',checkpoint=ROOT/'common.safetensors');model.save_checkpoint(ROOT/'common-reloaded.safetensors')
    assert sha(ROOT/'common-reloaded.safetensors')==sha(ROOT/'common.safetensors')
    replica,_=model.packed(ROOT/'common.mkqb');assert packet(ROOT/'common.mkqb')[1]==packet(WARMUP/'direct/step-250.mkqb')[1]
    replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
    write(ROOT/'common-meaning.json',diagnostics(replica,model.tokenizer,'development',model))
    write(ROOT/'common-planning.json',planning_diagnostics(replica,model.tokenizer,'development'))
    goals=read(ROOT/'goals.jsonl');random.Random(151701).shuffle(goals);goals=goals[:policy['train_plan_cache_goals']]
    write(ROOT/'cache-goal-keys.json',[g['key']for g in goals])
    plans=make_plans(replica,model.tokenizer,goals);write(ROOT/'common-self-plans.json',plans)
    for arm in ARMS:write(ROOT/('common-development-'+arm+'.json'),evaluate(replica,model.tokenizer,'development',arm))
    protected=warm['source_hashes'];names=sorted(set(protected)|{p.name for p in HERE.glob('an_*.py')if p.name not in ['an_remote.py','an_collect.py','an_verify.py','an_report.py','an_chat.py','an_native.py']})
    folder=ROOT/'training-source';folder.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,folder/n)
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':{str(p.relative_to(ROOT)):sha(p)for p in folder.iterdir()},
        'common_checkpoint_sha256':sha(ROOT/'common.safetensors'),'common_plans_sha256':sha(ROOT/'common-self-plans.json'),
        'probe':warm['probe'],'legacy_prompt_exact_examples':checked,'common_Q4_reload_exact':True,'preflight_optimizer_updates':0,
        'auxiliary_parameters':warm['auxiliary_parameters'],'deployed_parameter_count':3022080,'trainable_parameters':warm['trainable_parameters']})
    print(json.dumps({'preflight':'passed','legacy_prompt_checks':checked,'shared_checkpoint':sha(ROOT/'common.safetensors'),'cached_student_plans':len(plans)}),flush=True)


def train(arm):
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    out=ROOT/arm;out.mkdir(exist_ok=True);model=Agent(arm,checkpoint=ROOT/'common.safetensors');original=model.input_digest()
    model.save_checkpoint(out/'start.safetensors');assert sha(out/'start.safetensors')==prepared['common_checkpoint_sha256']
    teacher,tokenizer=load();course=Course(tokenizer,arm);course.plans=json.loads((ROOT/'common-self-plans.json').read_text());head=torch.tensor(body_ids(tokenizer),device='cuda')
    base=json.loads((ROOT/'initial-development.json').read_text())
    # Step zero of selection is the original released source, not the warmup.
    source=Agent(arm,probe=ROOT/'probe.safetensors');source.save_checkpoint(out/'best.safetensors');del source
    write(out/'best.json',{'step':0,'key':score(base,base),'sha256':sha(out/'best.safetensors'),'runtime_mode':'legacy'})
    adapters=[p for n,p in model.named_parameters()if p.requires_grad and n not in ['action_head','correct_head']and not n.startswith(('op_head.','binding_head.','error_head.'))]
    aux=list(model.op_head.parameters())+list(model.binding_head.parameters())+list(model.error_head.parameters())
    optimizer=torch.optim.AdamW([{'params':adapters,'lr_base':policy['lr_lora'],'weight_decay':.01},
        {'params':[model.action_head,model.correct_head],'lr_base':policy['lr_heads'],'weight_decay':0.},
        {'params':aux,'lr_base':policy['lr_aux'],'weight_decay':0.}])
    started=time.monotonic();research=None;losses=[]
    for step in range(1,policy['steps']+1):
        model.train();optimizer.zero_grad(set_to_none=True);factor=min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['lr_base']*factor
        batch,anchors=course.batch(step+250,'cuda')
        with torch.nn.utils.parametrize.cached(),torch.autocast('cuda',dtype=torch.bfloat16):
            value,parts=loss(model,batch,head,policy);keep,details=retention(model,teacher,anchors,head,policy);value+=policy['distill_weight']*keep;parts.update(details)
        assert torch.isfinite(value);value.backward();torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%25==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],'loss':sum(losses[-25:])/len(losses[-25:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==original;model.save_checkpoint(out/f'step-{step}.safetensors');replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(tokenizer))
            result=evaluate(replica,tokenizer,'development',arm);k=score(result,base);write(out/f'development-{step}.json',result)
            write(out/f'meaning-{step}.json',diagnostics(replica,tokenizer,'development',model));write(out/f'planning-{step}.json',planning_diagnostics(replica,tokenizer,'development'))
            if k>json.loads((out/'best.json').read_text())['key']:
                model.save_checkpoint(out/'best.safetensors');write(out/'best.json',{'step':step,'key':k,'sha256':sha(out/'best.safetensors'),'runtime_mode':arm})
            if research is None or k[1:]>research['key'][1:]:
                model.save_checkpoint(out/'research.safetensors');research={'step':step,'key':k,'sha256':sha(out/'research.safetensors'),'runtime_mode':arm};write(out/'research.json',research)
            if step in policy['plan_cache_updates']:
                ids=set(json.loads((ROOT/'cache-goal-keys.json').read_text()));goals=[g for g in read(ROOT/'goals.jsonl')if g['key']in ids]
                course.plans=make_plans(replica,tokenizer,goals);write(out/f'self-plans-{step}.json',course.plans)
            del replica;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'step':step,'key':k,'summary':brief(result)}),flush=True)
    assert model.input_digest()==original and all(p.grad is None for p in teacher.parameters());model.save_checkpoint(out/'last.safetensors')
    write(out/'training.json',{'steps':policy['steps'],'warmup_steps_in_model':250,'same_draw_digest':course.digest,'counts':dict(course.counts),
        'starting_checkpoint_sha256':sha(out/'start.safetensors'),'input_rows_unchanged':True,'teacher_frozen':True,'seconds':time.monotonic()-started})
    write(out/'status.json',{'phase':'trained','step':policy['steps']})


def audit(arm):
    assert(ROOT/'preselected.json').exists()
    for role in ['best','research']:
        metadata=json.loads((ROOT/arm/(role+'.json')).read_text());model=Agent(arm,checkpoint=ROOT/arm/(role+'.safetensors'))
        replica,_=model.packed(ROOT/arm/(role+'-audit.mkqb'));replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
        write(ROOT/arm/(role+'-fresh.json'),evaluate(replica,model.tokenizer,'fresh',metadata['runtime_mode']))
        write(ROOT/arm/(role+'-meaning-fresh.json'),diagnostics(replica,model.tokenizer,'fresh',model));write(ROOT/arm/(role+'-planning-fresh.json'),planning_diagnostics(replica,model.tokenizer,'fresh'))
        export_profile(model,ROOT/'export'/(arm+('-research'if role=='research'else'')),metadata);del model,replica;torch.cuda.empty_cache()
    write(ROOT/arm/'status.json',{'phase':'complete'})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','train','baseline','audit']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(151501);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    elif a.action=='audit':audit(a.arm)
    else:
        assert(ROOT/'preselected.json').exists();model,tokenizer=load();write(ROOT/'initial-fresh.json',evaluate(model,tokenizer,'fresh','legacy'))
        probe=Agent('direct',probe=ROOT/'probe.safetensors');write(ROOT/'initial-meaning-fresh.json',diagnostics(model,tokenizer,'fresh',probe));write(ROOT/'initial-planning-fresh.json',planning_diagnostics(model,tokenizer,'fresh'))
