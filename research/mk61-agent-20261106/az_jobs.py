"""Continue both prior adapters, select on fresh development, then sealed Q4."""
import argparse
import collections
import json
import math
import time
import torch
import ay_jobs as original
from az_common import ROOT,HERE,REPO,PARENT,SOURCES,ARMS,read,rows,write,sha,body_ids,output_ids,compact_head,check_frozen
from az_model import Agent,load
from az_course import Course,encoded,loss
from az_eval import evaluate,key,brief
from aq_course import pad
from native_export import packet


def prepare():
    assert not(ROOT/'prepared.json').exists()
    teacher=read(ROOT/'teacher-frozen.json');lessons=read(ROOT/'lessons-frozen.json')
    for n,d in teacher['files'].items():assert sha(ROOT/n)==d,n
    assert sha(ROOT/'lessons.jsonl')==lessons['sha256']
    assert lessons['RUN_counts']['0']==lessons['RUN_counts']['1']>0
    policy={'arms':ARMS,'steps':3000,'checkpoints':[500,1500,3000],'curriculum_steps':500,'batch':32,
        'batch_sources':{'goal':14,'repair':6,'run':6,'done':4,'unsure':2},
        'RUN_00_and_01_per_update':3,'lr_lora':.00015,'lr_actions':.0003,'body_weight':2.,
        'continued_existing_rank16_adapters':True,'LoRA_rank':16,'LoRA_alpha':32,'Q4_every_forward':True,
        'dtype':'FP32','context':1024,'max_turns':12,'same_data_draws_budget_and_objective':True,
        'same_start_between_arms':False,'start_reason':'each branch continues its own preselected v1 checkpoint',
        'selection':'known sin22 regression gate, then minimum primary known/novel and RUN00/01 accuracy, total primary, raw utility',
        'closed_used_for_selection':False,'teacher':'DeepSeek-V4.1-Flash wording and independent reverse check; ROM truth',
        'numeric_holdout_scope':'literal values absent from this and previous-round training ASTs; not a claim about all historical tokens',
        'scope':'straight-line arithmetic, optional result store; no branches or loops',
        'constant_pool':'v1 base plus extracted literals and their sign counterparts; some training pools permuted with distractors',
        'current_program_input':'HEX in both branches; SPEC input conversion not added',
        'new_risk_penalty_DPO_or_critic':False,'dictionary_frozen':True,'one_training_seed':True}
    write(ROOT/'policy.json',policy)
    agents={};tokenizer=None;parents={};gradient_checks={};cpu_differences={}
    for arm in ARMS:
        agent=Agent(arm,'cpu');agents[arm]=agent;tokenizer=agent.tokenizer
        agent.save_checkpoint(ROOT/('initial-'+arm+'.safetensors'))
        assert sha(ROOT/('initial-'+arm+'.safetensors'))==sha(ROOT/('parent-'+arm+'.safetensors'))
        replica,_=agent.packed(ROOT/('initial-'+arm+'.mkqb'))
        cpu_payload=packet(ROOT/('initial-'+arm+'.mkqb'))[1];published_payload=packet(SOURCES[arm]/'model.mkqb')[1]
        assert len(cpu_payload)==len(published_payload)
        cpu_differences[arm]=sum(x!=y for x,y in zip(cpu_payload,published_payload))
        del replica
        parents[arm]={str(p.relative_to(SOURCES[arm])):sha(p)for p in [SOURCES[arm]/'model.mkqb',*sorted((SOURCES[arm]/'hf').iterdir())]if p.is_file()}
    a,b=[agents[x].get_input_embeddings().weight for x in ARMS]
    assert torch.equal(a,b),'Frozen foundation dictionaries must match before continuation'
    values=rows(ROOT/'lessons.jsonl');valid=[];dropped=collections.Counter()
    for i,row in enumerate(values):
        original.no_answers(row['state']);both=[encoded(tokenizer,row,arm)for arm in ARMS]
        if max(len(v[0])for v in both)>1024:dropped[row['origin']]+=1;continue
        valid.append(i)
        if i%10000==0:print(json.dumps({'tokenized':i,'valid_both':len(valid)}),flush=True)
    assert len(valid)>.8*len(values)
    write(ROOT/'common-valid-ids.json',valid)
    indexes=[i for i in valid if values[i]['origin']=='goal'and values[i]['family']=='constant'][:2]
    assert len(indexes)==2
    for arm,agent in agents.items():
        batch=pad([encoded(tokenizer,values[i],arm)for i in indexes],'cpu')
        agent.zero_grad(set_to_none=True);v,_=loss(agent,batch,torch.tensor(body_ids(tokenizer)));v.backward()
        assert torch.isfinite(v)and all(torch.isfinite(p.grad).all()for p in agent.parameters()if p.grad is not None)
        assert agent.get_input_embeddings().weight.grad is None
        gradient_checks[arm]={'finite':True,'optimizer_updates':0,'loss':float(v.detach())}
        agent.zero_grad(set_to_none=True)
    write(ROOT/'preflight-gradients.json',gradient_checks)
    files=['policy.json','ast-frozen.json','teacher-frozen.json','lessons-frozen.json','lessons.jsonl','codec-checks.json',
           'train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl','common-valid-ids.json','preflight-gradients.json']
    for arm in ARMS:files += ['parent-'+arm+'.safetensors','initial-'+arm+'.safetensors','initial-'+arm+'.mkqb']
    excluded=lambda p:p.name.endswith(('_report.py','_remote.py'))or p.name in ['ay_native.py','az_native.py']
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not excluded(p)}
    external=[p for p in(ROOT.parent/'full-isa-v1/core-source').rglob('*')if p.is_file()]+[HERE/'full_isa_bridge.cpp',HERE/'core_bridge.cpp']
    # The original frozen AQ base remains the factorization base for both adapters.
    from ay_common import INITIAL as foundation
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,'files':{n:sha(ROOT/n)for n in files},'parents':parents,
       'external_sources':{str(p.relative_to(REPO)):sha(p)for p in external if p.is_file()},
       'foundation_files':{str(p.relative_to(foundation)):sha(p)for p in [foundation/'model.mkqb',*sorted((foundation/'hf').iterdir())]if p.is_file()},
       'closed_model_generations_seen':False,'SGD_started':False})
    write(ROOT/'prepared.json',{'valid_lessons':len(valid),'total_lessons':len(values),'dropped_for_both':dict(dropped),
       'trainable_parameters':agents['hex'].trainable_count(),'parameters_after_merge':3022080,
       'CPU_reconstruction_payload_byte_differences':cpu_differences,'B200_initial_Q4_exact_required_before_SGD':True,
       'continued_parent_adapter_files_exact':True,
       'same_frozen_input_dictionary':True,'preflight_optimizer_updates':0})
    check_frozen();print(json.dumps({'prepared':True,'lessons':len(valid),'parents_exact':True,'test_sealed':True}),flush=True)


def train(arm):
    check_frozen();policy=read(ROOT/'policy.json');out=ROOT/arm;out.mkdir(exist_ok=True)
    initial=ROOT/('initial-'+arm+'.safetensors');model=Agent(arm,checkpoint=initial);frozen_input=model.input_digest()
    model.save_checkpoint(out/'start.safetensors');assert sha(out/'start.safetensors')==sha(initial)
    # A CPU GEMM can cross an FP32 quantization boundary when reconstructing LoRA.
    # The training device must reproduce the published starting Q4 payload exactly.
    replica,_=model.packed(out/'start.mkqb')
    assert packet(out/'start.mkqb')[1]==packet(SOURCES[arm]/'model.mkqb')[1],arm
    del replica;torch.cuda.empty_cache()
    write(out/'initial-Q4-receipt.json',{'B200_reconstruction_exact':True,'optimizer_updates':0,
       'parent_packet_sha256':sha(SOURCES[arm]/'model.mkqb'),'start_packet_sha256':sha(out/'start.mkqb')})
    course=Course(model.tokenizer,arm);head=torch.tensor(body_ids(model.tokenizer),device='cuda')
    adapters=[p for n,p in model.named_parameters()if p.requires_grad and n!='action_head']
    optimizer=torch.optim.AdamW([{'params':adapters,'base_lr':policy['lr_lora'],'weight_decay':.01},
                               {'params':[model.action_head],'base_lr':policy['lr_actions'],'weight_decay':0.}])
    best=None;started=time.monotonic();losses=[]
    for step in range(1,policy['steps']+1):
        optimizer.zero_grad(set_to_none=True);factor=min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,course.batch(step,'cuda'),head)
        assert torch.isfinite(value);value.backward();assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],
               'loss':sum(losses[-50:])/len(losses[-50:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==frozen_input;model.save_checkpoint(out/f'step-{step}.safetensors')
            replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
            result=evaluate(replica,model.tokenizer,'development',arm);k=key(result);write(out/f'development-{step}.json',result)
            if best is None or k>best['key']:
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':k,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'step':step,'key':k,'development':brief(result),'sin22':result['regression']['passed']}),flush=True)
    model.save_checkpoint(out/'last.safetensors');assert model.input_digest()==frozen_input
    assert course.counts['RUN_0']==course.counts['RUN_1']==policy['steps']*3
    write(out/'training.json',{'steps':policy['steps'],'optimizer_updates':policy['steps'],'same_draw_digest':course.digest,
      'counts':dict(course.counts),'starting_checkpoint_sha256':sha(out/'start.safetensors'),
      'parent_packet_sha256':sha(SOURCES[arm]/'model.mkqb'),'input_rows_frozen':True,
      'actual_B200_initial_Q4_exact':True,
      'trainable_parameters':model.trainable_count(),'seconds':time.monotonic()-started})
    write(out/'status.json',{'phase':'trained','step':policy['steps']});check_frozen()


def configure(arm):
    original.ROOT=ROOT;original.check_frozen=check_frozen;original.evaluate=evaluate
    original.Agent=lambda device='cuda',checkpoint=None:Agent(arm,device,checkpoint)
    original.load=lambda device='cuda':load(arm,device)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','train','audit','baseline']);p.add_argument('--arm',choices=ARMS);a=p.parse_args()
    torch.set_num_threads(4);torch.manual_seed(26110825);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    else:
        configure(a.arm)
        if a.action=='audit':
            original.audit(a.arm)
            folder=ROOT/'export'/a.arm
            for name in ['protocol.json','manifest.json']:
                metadata=read(folder/name);metadata.update(experiment='semantic-spec-distill-v2',continued_parent_packet_sha256=sha(SOURCES[a.arm]/'model.mkqb'))
                write(folder/name,metadata)
        else:original.baseline(a.arm)
