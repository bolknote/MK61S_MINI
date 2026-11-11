"""Two SPEC continuations, development-only selection, fresh closed Q4 exam."""
import argparse
import collections
import json
import math
import shutil
import time
import torch
from ba_common import ROOT,HERE,REPO,SOURCE,RUNS,read,rows,write,sha,check_frozen,body_ids,output_ids,compact_head,ACTIONS,ACTION_IDS,CORRECT_IDS
from ba_model import Agent,load
from ba_course import Course,encoded,loss
from ba_pools import lesson_layout
from ba_eval import evaluate,key,brief
from ay_jobs import no_answers
from aq_course import pad
from aq_protocol import header_ids
from native_export import packet


def prepare():
    assert not(ROOT/'prepared.json').exists()
    t=read(ROOT/'teacher-frozen.json');l=read(ROOT/'lessons-frozen.json')
    for n,d in t['files'].items():assert sha(ROOT/n)==d,n
    assert sha(ROOT/'lessons.jsonl')==l['sha256']
    policy={'steps':4000,'checkpoints':[1000,2500,4000],'binding_steps':600,'batch':32,
       'seeds':{'seed-a':26110851,'seed-b':26110852},'lr_lora':.00015,'lr_actions':.00015,'body_weight':2.,
       'continued_rank16':True,'rank':16,'alpha':32,'Q4_every_forward':True,'dtype':'FP32','context':1024,
       'binding_batch':'12 literal copy +12 goal +4 hard repair +2 RUN +2 DONE',
       'joint_batch':'12 paired goals +8 paired repairs +4 RUN +4 DONE +4 UNSURE',
       'pair_views':'same lesson: default/extras and full/distractors, re-sampled every draw',
       'errors':'same program/different condition; stopped-but-wrong mutations; retired old exam mistakes; train-only parent mining',
       'unchanged_actor_input_and_tool_protocol':True,'input_current_program':'HEX as before','no_new_critic_DPO_or_risk_penalty':True,
       'selection':'retain primary and raw success within3pp and navigation within1; keep known sin22; prefer joint lower falseDONE and >=10pp worst permutation gain; minimize falseDONE then worst permutation accuracy and successful completion',
       'parent_is_fallback_candidate':True,'closed_used_for_selection':False,
       'old_exam_errors_retired_into_training':True,'new_closed_prior_questions_and_signatures_excluded':True,
       'scope':'straight-line arithmetic with optional result store; no general control flow'}
    write(ROOT/'policy.json',policy);agent=Agent('cpu');agent.save_checkpoint(ROOT/'initial.safetensors')
    assert sha(ROOT/'initial.safetensors')==sha(ROOT/'parent.safetensors')
    replica,_=agent.packed(ROOT/'initial-CPU.mkqb');del replica
    cpu=packet(ROOT/'initial-CPU.mkqb')[1];parent=packet(SOURCE/'model.mkqb')[1]
    assert len(cpu)==len(parent);different=sum(a!=b for a,b in zip(cpu,parent))
    values=rows(ROOT/'lessons.jsonl');valid=[];dropped=collections.Counter()
    for i,row in enumerate(values):
        no_answers(row['state'])
        if row['state'].get('diagnosis'):dropped['diagnosis']+=1;continue
        transformed=[lesson_layout(row,m,f'preflight:{i}:{m}')for m in ['default','full','distractors']]
        if max(len(encoded(agent.tokenizer,r,'spec')[0])for r in transformed)>1000:dropped[row['origin']]+=1;continue
        valid.append(i)
        if i%10000==0:print(json.dumps({'tokenized':i,'valid':len(valid)}),flush=True)
    assert len(valid)>.85*len(values);write(ROOT/'valid-ids.json',valid)
    batch_rows=[lesson_layout(values[i],'full',f'gradient:{i}')for i in valid if values[i]['origin']=='goal'][:2]
    agent.zero_grad(set_to_none=True);value,_=loss(agent,pad([encoded(agent.tokenizer,r,'spec')for r in batch_rows],'cpu'),torch.tensor(body_ids(agent.tokenizer)));value.backward()
    assert torch.isfinite(value)and all(torch.isfinite(p.grad).all()for p in agent.parameters()if p.grad is not None)
    assert agent.get_input_embeddings().weight.grad is None
    write(ROOT/'gradient-preflight.json',{'finite':True,'loss':float(value.detach()),'optimizer_updates':0})
    files=['ast-frozen.json','teacher-frozen.json','lessons-frozen.json','lessons.jsonl','policy.json','checks.json','valid-ids.json',
      'train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl','parent.safetensors','initial.safetensors','initial-CPU.mkqb','gradient-preflight.json',
      'mined-0.json','mined-0.jsonl','mined-1.json','mined-1.jsonl']
    excluded=lambda p:p.name.endswith(('_report.py','_remote.py','_native.py'))
    from ay_common import INITIAL
    def assets(folder):return {str(p.relative_to(folder)):sha(p)for p in [folder/'model.mkqb',*sorted((folder/'hf').iterdir())]if p.is_file()}
    external=[p for p in(ROOT.parent/'full-isa-v1/core-source').rglob('*')if p.is_file()]+[HERE/'full_isa_bridge.cpp',HERE/'core_bridge.cpp']
    write(ROOT/'frozen.json',{'sources':{p.name:sha(p)for p in HERE.glob('*.py')if not excluded(p)},'files':{n:sha(ROOT/n)for n in files},
        'parent':assets(SOURCE),'foundation':assets(INITIAL),'external_sources':{str(p.relative_to(REPO)):sha(p)for p in external},
        'SGD_started':False,'closed_model_generations_seen':False,'mining_only_training_goals':True,'unix':time.time()})
    write(ROOT/'prepared.json',{'valid_lessons':len(valid),'total_lessons':len(values),'dropped':dict(dropped),'CPU_initial_Q4_byte_differences':different,
       'trainable_parameters':agent.trainable_count(),'parameters':3022080,'parent_adapter_exact':True,'B200_Q4_exact_required_before_SGD':True})
    check_frozen();print(json.dumps({'prepared':True,'valid_lessons':len(valid),'test_sealed':True}),flush=True)


def baseline_development():
    check_frozen();model,tokenizer=load();compact_head(model,output_ids(tokenizer));result=evaluate(model,tokenizer,'development')
    write(ROOT/'parent-development.json',result);write(ROOT/'baseline-receipt.json',{'sha256':sha(ROOT/'parent-development.json'),
        'parent_packet_sha256':sha(SOURCE/'model.mkqb'),'closed_opened':False,'optimizer_updates':0})
    print(json.dumps({'parent_development':brief(result)}),flush=True)


def train(run):
    check_frozen();policy=read(ROOT/'policy.json');out=ROOT/run;out.mkdir(exist_ok=True)
    assert sha(ROOT/'parent-development.json')==read(ROOT/'baseline-receipt.json')['sha256'];parent=read(ROOT/'parent-development.json')
    torch.manual_seed(policy['seeds'][run]);model=Agent(checkpoint=ROOT/'initial.safetensors');input_digest=model.input_digest()
    model.save_checkpoint(out/'start.safetensors');assert sha(out/'start.safetensors')==sha(ROOT/'parent.safetensors')
    replica,_=model.packed(out/'start.mkqb');del replica
    assert packet(out/'start.mkqb')[1]==packet(SOURCE/'model.mkqb')[1]
    write(out/'initial-receipt.json',{'B200_initial_Q4_exact':True,'optimizer_updates':0,'parent_packet_sha256':sha(SOURCE/'model.mkqb')})
    course=Course(model.tokenizer,run);head=torch.tensor(body_ids(model.tokenizer),device='cuda')
    adapters=[p for n,p in model.named_parameters()if p.requires_grad and n!='action_head']
    optimizer=torch.optim.AdamW([{'params':adapters,'base_lr':policy['lr_lora'],'weight_decay':.01},
        {'params':[model.action_head],'base_lr':policy['lr_actions'],'weight_decay':0.}])
    model.save_checkpoint(out/'best.safetensors');best={'step':0,'key':key(parent,parent),'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
    losses=[];started=time.monotonic()
    for step in range(1,policy['steps']+1):
        optimizer.zero_grad(set_to_none=True);factor=min(1.,step/100)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,course.batch(step,'cuda'),head)
        assert torch.isfinite(value);value.backward();assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],
            'loss':sum(losses[-50:])/len(losses[-50:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==input_digest;model.save_checkpoint(out/f'step-{step}.safetensors')
            replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
            result=evaluate(replica,model.tokenizer,'development');score=key(result,parent);write(out/f'development-{step}.json',result)
            if score>best['key']:
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':score,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache();print(json.dumps({'run':run,'step':step,'key':score,'development':brief(result)}),flush=True)
    model.save_checkpoint(out/'last.safetensors');assert model.input_digest()==input_digest
    assert course.counts['RUN_0']==course.counts['RUN_1']==policy['binding_steps']+2*(policy['steps']-policy['binding_steps'])
    write(out/'training.json',{'steps':policy['steps'],'optimizer_updates':policy['steps'],'seed':policy['seeds'][run],
      'counts':dict(course.counts),'draw_digest':course.digest,'initial_Q4_exact':True,'input_dictionary_frozen':True,
      'starting_checkpoint_sha256':sha(out/'start.safetensors'),'seconds':time.monotonic()-started})
    write(out/'status.json',{'phase':'trained','step':policy['steps']});check_frozen()


def audit(which):
    check_frozen();selection=read(ROOT/'preselected.json');out=ROOT/which;out.mkdir(exist_ok=True);folder=ROOT/'export'/which;folder.mkdir(parents=True,exist_ok=True)
    if which=='parent':
        model,tokenizer=load()
        shutil.copytree(SOURCE/'hf',folder/'hf',dirs_exist_ok=True)
        for name in ['model.mkqb','manifest.json','protocol.json']:shutil.copyfile(SOURCE/name,folder/name)
    else:
        choice=selection['selected'];agent=Agent(checkpoint=ROOT/choice['run']/'best.safetensors');tokenizer=agent.tokenizer
        model,_=agent.packed(folder/'model.mkqb');master=agent.merged_master();master.save_pretrained(folder/'hf',safe_serialization=True);tokenizer.save_pretrained(folder/'hf')
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':3022080,
            'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,'selected_step':choice['step'],
            'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'selection_used_closed_test':False})
        write(folder/'protocol.json',{'kind':'semantic-spec-grounding-v1','arm':'spec','context':1024,'codec':'ay_codec.py',
            'actions':ACTIONS,'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,
            'neural_headers':{a:header_ids(tokenizer,a)for a in ['write','run','diag']}})
    model.cuda().eval();compact_head(model,output_ids(tokenizer));result=evaluate(model,tokenizer,'closed');write(out/'closed.json',result)
    write(folder/'output-token-ids.json',output_ids(tokenizer));write(out/'status.json',{'phase':'complete'});check_frozen()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','baseline-development','train','audit']);p.add_argument('--run',choices=RUNS);p.add_argument('--which',choices=['parent','spec']);a=p.parse_args()
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='baseline-development':baseline_development()
    elif a.action=='train':train(a.run)
    else:audit(a.which)
