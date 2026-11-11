"""Frozen matched-context Q4 training, controlled selection and sealed exam."""
import argparse
import collections
import json
import math
import shutil
import time
import torch
from aq_common import ROOT,PARENT,HERE,INITIAL,INITIAL_PACKET,ARMS,ACTIONS,ACTION_IDS,CORRECT_IDS,read,write,sha,body_ids,output_ids,compact_head
from aq_model import Agent,load
from aq_course import Course,encoded,loss
from aq_eval import evaluate,key,brief
from aq_runtime import render
from aq_protocol import prompt_ids,header_ids
from native_quant import attach,export
from native_export import packet


def no_answers(value):
    if isinstance(value,dict):
        assert not set(value)&{'expected','hidden_tests','reference_code'}
        for v in value.values():no_answers(v)
    elif isinstance(value,list):
        for v in value:no_answers(v)


def prepare():
    frozen=json.loads((ROOT/'data-frozen.json').read_text())
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    extra=json.loads((ROOT/'external-data-frozen.json').read_text())
    for n,d in extra['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.safetensors')==frozen['source_master_sha256']and sha(INITIAL_PACKET)==frozen['source_packet_sha256']
    old=json.loads((PARENT/'prepared.json').read_text())['source_hashes']
    for n,d in old.items():assert sha(HERE/n)==d,n
    model=Agent('cpu');tokenizer=model.tokenizer;rows=read(ROOT/'lessons.jsonl')+read(ROOT/'extra-lessons.jsonl');valid=[];lengths=[];dropped=collections.Counter()
    for i,r in enumerate(rows):
        no_answers(r['state']);full=encoded(tokenizer,r,'full');short=encoded(tokenizer,r,'short')
        assert not set(prompt_ids(tokenizer,render(r['state'],'full')))&set(ACTION_IDS+CORRECT_IDS)
        if max(len(full[0]),len(short[0]))>1024:dropped[r['origin']]+=1;continue
        valid.append(i);lengths.append([full[2]+1,short[2]+1])
        if i%5000==0:print(json.dumps({'tokenized_lessons':i,'common_valid':len(valid)}),flush=True)
    assert len(valid)>.8*len(rows)
    write(ROOT/'common-valid-lesson-ids.json',valid)
    model.save_checkpoint(ROOT/'initial.safetensors');replica,_=model.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(INITIAL_PACKET)[1]
    del replica,model
    # Both arms start from exactly one saved set of factors and head rows.
    a=Agent('cpu',ROOT/'initial.safetensors');a.save_checkpoint(ROOT/'initial-reloaded.safetensors')
    assert sha(ROOT/'initial.safetensors')==sha(ROOT/'initial-reloaded.safetensors')
    for arm in ARMS:
        course=Course(tokenizer,arm);course.batch(1,'cpu')
    import statistics
    stats={'full_min_median_max':[min(x[0]for x in lengths),statistics.median(x[0]for x in lengths),max(x[0]for x in lengths)],
      'short_min_median_max':[min(x[1]for x in lengths),statistics.median(x[1]for x in lengths),max(x[1]for x in lengths)],
      'saved_min_median_max':[min(x[0]-x[1]for x in lengths),statistics.median(x[0]-x[1]for x in lengths),max(x[0]-x[1]for x in lengths)]}
    write(ROOT/'prompt-budget.json',stats)
    excluded={'aq_remote.py','aq_collect.py','aq_verify.py','aq_report.py','aq_native.py','aq_chat.py'}
    names=sorted(set(old)|{p.name for p in HERE.glob('aq_*.py')if p.name not in excluded})
    folder=ROOT/'training-source';folder.mkdir(exist_ok=True)
    for n in names:shutil.copyfile(HERE/n,folder/n)
    protected_files={str(p.relative_to(ROOT)):sha(p)for p in folder.iterdir()}
    protected_files.update({n:sha(ROOT/n)for n in ['common-valid-lesson-ids.json','initial.safetensors','initial.mkqb','prompt-budget.json']})
    protected_files.update({n:sha(ROOT/n)for n in ['external-data-frozen.json','extra-lessons.jsonl']})
    write(ROOT/'prepared.json',{'source_hashes':{n:sha(HERE/n)for n in names},'files':protected_files,
      'initial_checkpoint_sha256':sha(ROOT/'initial.safetensors'),'source_Q4_payload_exact':True,
      'common_valid_lessons':len(valid),'total_course_rows':len(rows),'dropped_for_both_arms':dict(dropped),'prompt_budget':stats,
      'trainable_parameters':a.trainable_count(),'input_dictionary_frozen':True,'preflight_optimizer_updates':0})
    print(json.dumps({'preflight':'passed','trainable':a.trainable_count(),'valid_lessons':len(valid),'dropped':dict(dropped),'prompt_budget':stats}),flush=True)


def train(arm):
    policy=json.loads((ROOT/'policy.json').read_text());prepared=json.loads((ROOT/'prepared.json').read_text())
    for n,d in prepared['source_hashes'].items():assert sha(HERE/n)==d,n
    out=ROOT/arm;out.mkdir(exist_ok=True);model=Agent(checkpoint=ROOT/'initial.safetensors');original=model.input_digest()
    model.save_checkpoint(out/'start.safetensors');assert sha(out/'start.safetensors')==prepared['initial_checkpoint_sha256']
    teacher,tokenizer=load();course=Course(tokenizer,arm);head=torch.tensor(body_ids(tokenizer),device='cuda')
    adapters=[p for n,p in model.named_parameters()if p.requires_grad and n not in ['action_head','correct_head']]
    optimizer=torch.optim.AdamW([{'params':adapters,'lr_base':policy['lr_lora'],'weight_decay':.01},
      {'params':[model.action_head,model.correct_head],'lr_base':policy['lr_heads'],'weight_decay':0.}])
    best=None;started=time.monotonic();losses=[]
    for step in range(1,policy['steps']+1):
        optimizer.zero_grad(set_to_none=True);factor=min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['lr_base']*factor
        batch,tbatch,weights,truth=course.batch(step,'cuda')
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,teacher,batch,tbatch,weights,truth,head,policy)
        assert torch.isfinite(value);value.backward()
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],'loss':sum(losses[-50:])/len(losses[-50:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==original;model.save_checkpoint(out/f'step-{step}.safetensors')
            replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(tokenizer))
            result=evaluate(replica,tokenizer,'development',arm);k=key(result);write(out/f'development-{step}.json',result)
            if step in policy['selectable_checkpoints'] and (best is None or k>best['key']):
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':k,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'step':step,'key':k,'control':brief(result)}),flush=True)
    model.save_checkpoint(out/'last.safetensors');assert model.input_digest()==original and all(p.grad is None for p in teacher.parameters())
    write(out/'training.json',{'steps':policy['steps'],'same_draw_digest':course.digest,'counts':dict(course.counts),'starting_checkpoint_sha256':sha(out/'start.safetensors'),
      'trainable_parameters':model.trainable_count(),'input_rows_frozen':True,'teacher_frozen':True,'seconds':time.monotonic()-started})
    write(out/'status.json',{'phase':'trained','step':policy['steps']})


def export_role(arm,role):
    assert(ROOT/'preselected.json').exists()
    policy=json.loads((ROOT/'policy.json').read_text())
    metadata=json.loads((ROOT/arm/'best.json').read_text())if role=='best'else{'step':policy['steps'],'fixed_endpoint_predeclared':True,'not_used_for_selection':True}
    checkpoint=ROOT/arm/('best.safetensors'if role=='best'else f"step-{policy['steps']}.safetensors")
    agent=Agent(checkpoint=checkpoint);folder=ROOT/'export'/(arm if role=='best'else arm+'-terminal');folder.mkdir(parents=True,exist_ok=True)
    model,_=agent.packed(folder/'model.mkqb');model.cuda().eval();compact_head(model,output_ids(agent.tokenizer))
    write(ROOT/arm/('fresh.json'if role=='best'else'terminal-fresh.json'),evaluate(model,agent.tokenizer,'fresh',arm))
    master=agent.merged_master();assert sum(p.numel()for p in master.parameters())==3022080
    master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf');attach(master,'q4');export(master,folder/'model.mkqb','q4')
    write(folder/'output-token-ids.json',output_ids(agent.tokenizer));write(folder/'protocol.json',{'kind':'mk61-step-debug-v2','format_arm':arm,'actions':ACTIONS,
      'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,'context':1024,'neural_headers':{a:header_ids(agent.tokenizer,a)for a in ['write','run','diag']},
      'diagnosis':'TT HH LL AA BB; correct/op/arg/order, index, actual, proposed','external_semantic_veto':False})
    write(folder/'manifest.json',{'arm':'asm','quantization_mode':'q4','parameter_count':3022080,'packed_sha256':sha(folder/'model.mkqb'),
      'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},**metadata})


def audit(arm):
    export_role(arm,'best')
    policy=json.loads((ROOT/'policy.json').read_text());best=json.loads((ROOT/arm/'best.json').read_text())
    if best['step']==policy['steps']:
        shutil.copyfile(ROOT/arm/'fresh.json',ROOT/arm/'terminal-fresh.json')
        shutil.copytree(ROOT/'export'/arm,ROOT/'export'/(arm+'-terminal'),dirs_exist_ok=True)
    else:export_role(arm,'terminal')
    write(ROOT/arm/'status.json',{'phase':'complete'})


def baseline(arm):
    model,tokenizer=load();compact_head(model,output_ids(tokenizer));split='fresh'if(ROOT/'preselected.json').exists()else'development'
    write(ROOT/('initial-'+arm+'-'+split+'.json'),evaluate(model,tokenizer,split,arm))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','train','audit','baseline']);ap.add_argument('--arm',choices=ARMS);a=ap.parse_args()
    torch.set_num_threads(4);torch.manual_seed(171501);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    elif a.action=='audit':audit(a.arm)
    else:baseline(a.arm)
