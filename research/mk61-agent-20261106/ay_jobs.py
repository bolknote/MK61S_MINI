"""Matched QAT, development-only choice and a once-opened sealed Q4 exam."""
import argparse
import collections
import json
import math
import shutil
import time
import torch
from ay_common import ROOT,HERE,REPO,INITIAL,ARMS,read,rows,write,save_rows,sha,body_ids,output_ids,compact_head,check_frozen
from ay_model import Agent,load
from ay_course import Course,encoded,loss
from ay_eval import evaluate,key,brief
from ay_codec import UNARY_NAMES,BINARY_NAMES
from aq_course import pad
from native_export import packet
from aq_protocol import header_ids
from ay_common import ACTIONS,ACTION_IDS,CORRECT_IDS
from native_quant import attach,export


def no_answers(value):
    if isinstance(value,dict):
        assert not set(value)&{'expected','hidden_tests','reference_code','spec'}
        for v in value.values():no_answers(v)
    elif isinstance(value,list):
        for v in value:no_answers(v)


def prepare():
    assert not(ROOT/'prepared.json').exists()
    for item in ['ast-frozen.json','teacher-frozen.json','data-clean.json','lessons-frozen.json','codec-checks.json']:assert(ROOT/item).exists(),item
    teacher=read(ROOT/'teacher-frozen.json')
    for n,d in teacher['files'].items():assert sha(ROOT/n)==d,n
    assert sha(ROOT/'lessons.jsonl')==read(ROOT/'lessons-frozen.json')['sha256']
    policy={'arms':ARMS,'steps':3000,'checkpoints':[500,1500,3000],'curriculum_steps':500,'batch':32,
      'batch_sources':{'goal':16,'repair':8,'run':2,'done':4,'unsure':2},
      'lr_lora':.00015,'lr_actions':.0003,'body_weight':2.,'LoRA_rank':16,'LoRA_alpha':32,
      'Q4_every_forward':True,'training_dtype':'FP32','context':1024,'max_turns':12,
      'selection':'minimum known/novel development one-shot rate, total one-shot successes, raw repair utility, -false DONE',
      'closed_test_not_for_selection':True,'same_start_data_draws_steps_and_loss':True,
      'same_HEX_syntax_only_grammar':True,'spec_structural_constraints_used_during_generation':False,
      'fixed_input_dictionary':True,'auxiliary_correctness_head_trained':False,'DPO_risk_penalty_critic_KD':False,
      'runtime_control_goals':32,'closed_runtime_goals':128,
      'model_source':'AQ full selected step2500','teacher':'DeepSeek-V4.1-Flash wording plus independent reverse verification; ROM action labels',
      'scope':'straight-line arithmetic, one optional result store; no loops/branches',
      'novel_means':'held out of this training round; not claimed absent from all historical pretraining'}
    write(ROOT/'policy.json',policy)
    agent=Agent('cpu');tokenizer=agent.tokenizer;lessons=rows(ROOT/'lessons.jsonl');valid=[];dropped=collections.Counter();lengths=[]
    for i,row in enumerate(lessons):
        no_answers(row['state']);enc=[encoded(tokenizer,row,a)for a in ARMS]
        if max(len(x[0])for x in enc)>1024:dropped[row['origin']]+=1;continue
        valid.append(i);lengths.append([len(x[0])for x in enc])
        if i%5000==0:print(json.dumps({'tokenized':i,'valid_both':len(valid)}),flush=True)
    assert len(valid)>.8*len(lessons)
    write(ROOT/'common-valid-ids.json',valid)
    agent.save_checkpoint(ROOT/'initial.safetensors');replica,metadata=agent.packed(ROOT/'initial.mkqb')
    assert packet(ROOT/'initial.mkqb')[1]==packet(INITIAL/'model.mkqb')[1],'Initial Q4 changed'
    replica.requires_grad_(False);del replica
    # Test genuine gradients for both targets, without any optimizer update.
    gradients={}
    indexes=[i for i in valid if lessons[i]['origin']=='goal'][:2]
    for arm in ARMS:
        agent.zero_grad(set_to_none=True);batch=pad([encoded(tokenizer,lessons[i],arm)for i in indexes],'cpu')
        value,parts=loss(agent,batch,torch.tensor(body_ids(tokenizer)));assert torch.isfinite(value)
        value.backward();assert all(torch.isfinite(p.grad).all()for p in agent.parameters()if p.grad is not None)
        assert agent.get_input_embeddings().weight.grad is None
        gradients[arm]={'loss':float(value.detach()),'finite':True,'optimizer_updates':0}
    write(ROOT/'preflight-gradients.json',gradients);agent.zero_grad(set_to_none=True)
    files=['policy.json','common-valid-ids.json','initial.safetensors','initial.mkqb','preflight-gradients.json',
           'codec-checks.json','ast-frozen.json','teacher-frozen.json','lessons-frozen.json','lessons.jsonl',
           'train-goals.jsonl','development-goals.jsonl','closed-goals.jsonl',
           'data-clean.json','train-clean.jsonl','development-clean.jsonl','closed-clean.jsonl']
    excluded=lambda p:p.name.endswith(('_report.py','_remote.py'))or p.name=='ay_native.py'
    sources={p.name:sha(p)for p in HERE.glob('*.py')if not excluded(p)}
    external=[p for p in(ROOT.parent/'full-isa-v1/core-source').rglob('*')if p.is_file()]
    external += [HERE/'full_isa_bridge.cpp',HERE/'core_bridge.cpp']
    write(ROOT/'frozen.json',{'unix':time.time(),'files':{n:sha(ROOT/n)for n in files},'sources':sources,
                             'initial_packet_sha256':sha(INITIAL/'model.mkqb'),'initial_master_sha256':sha(INITIAL/'hf/model.safetensors'),
                             'initial_hf_files':{p.name:sha(p)for p in(INITIAL/'hf').iterdir()if p.is_file()},
                             'external_sources':{str(p.relative_to(REPO)):sha(p)for p in external},
                             'closed_model_generations_seen':False,'SGD_started':False})
    write(ROOT/'prepared.json',{'valid_lessons':len(valid),'total_lessons':len(lessons),'dropped_for_both':dict(dropped),
                              'trainable_parameters':agent.trainable_count(),'parameters_after_merge':3022080,
                              'initial_checkpoint_sha256':sha(ROOT/'initial.safetensors'),
                              'input_rows_frozen':True,'source_Q4_payload_exact':True,'preflight_optimizer_updates':0})
    check_frozen();print(json.dumps({'prepared':True,'lessons':len(valid),'trainable':agent.trainable_count(),'closed_exam_sealed':True}),flush=True)


def train(arm):
    check_frozen();policy=read(ROOT/'policy.json');out=ROOT/arm;out.mkdir(exist_ok=True)
    model=Agent(checkpoint=ROOT/'initial.safetensors');original=model.input_digest();model.save_checkpoint(out/'start.safetensors')
    assert sha(out/'start.safetensors')==sha(ROOT/'initial.safetensors')
    course=Course(model.tokenizer,arm);head=torch.tensor(body_ids(model.tokenizer),device='cuda')
    adapters=[p for n,p in model.named_parameters()if p.requires_grad and n!='action_head']
    optimizer=torch.optim.AdamW([{'params':adapters,'base_lr':policy['lr_lora'],'weight_decay':.01},
                               {'params':[model.action_head],'base_lr':policy['lr_actions'],'weight_decay':0.}])
    best=None;started=time.monotonic();losses=[]
    for step in range(1,policy['steps']+1):
        optimizer.zero_grad(set_to_none=True)
        factor=min(1.,step/50)*(.25+.75*(1+math.cos(math.pi*step/policy['steps']))/2)
        for group in optimizer.param_groups:group['lr']=group['base_lr']*factor
        with torch.nn.utils.parametrize.cached():value,parts=loss(model,course.batch(step,'cuda'),head)
        assert torch.isfinite(value);value.backward()
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters()if p.requires_grad],1.);optimizer.step();losses.append(float(value.detach()))
        if step==1 or step%50==0:write(out/'status.json',{'phase':'training','step':step,'steps':policy['steps'],
             'loss':sum(losses[-50:])/len(losses[-50:]),'parts':parts,'seconds':time.monotonic()-started})
        if step in policy['checkpoints']:
            assert model.input_digest()==original;model.save_checkpoint(out/f'step-{step}.safetensors')
            replica,_=model.packed(out/f'step-{step}.mkqb');replica.cuda().eval();compact_head(replica,output_ids(model.tokenizer))
            report=evaluate(replica,model.tokenizer,'development',arm);k=key(report);write(out/f'development-{step}.json',report)
            if best is None or k>best['key']:
                model.save_checkpoint(out/'best.safetensors');best={'step':step,'key':k,'sha256':sha(out/'best.safetensors')};write(out/'best.json',best)
            del replica;torch.cuda.empty_cache();print(json.dumps({'arm':arm,'step':step,'key':k,'development':brief(report)}),flush=True)
    model.save_checkpoint(out/'last.safetensors');assert model.input_digest()==original
    write(out/'training.json',{'steps':policy['steps'],'same_draw_digest':course.digest,'counts':dict(course.counts),
        'starting_checkpoint_sha256':sha(out/'start.safetensors'),'trainable_parameters':model.trainable_count(),
        'input_rows_frozen':True,'seconds':time.monotonic()-started,'optimizer_updates':policy['steps']})
    write(out/'status.json',{'phase':'trained','step':policy['steps']});check_frozen()


def audit(arm):
    assert(ROOT/'preselected.json').exists();check_frozen();out=ROOT/arm;folder=ROOT/'export'/arm;folder.mkdir(parents=True,exist_ok=True)
    choice=read(out/'best.json');agent=Agent(checkpoint=out/'best.safetensors')
    model,metadata=agent.packed(folder/'model.mkqb');model.cuda().eval();compact_head(model,output_ids(agent.tokenizer))
    result=evaluate(model,agent.tokenizer,'closed',arm);write(out/'closed.json',result)
    master=agent.merged_master();assert sum(p.numel()for p in master.parameters())==3022080
    master.save_pretrained(folder/'hf',safe_serialization=True);agent.tokenizer.save_pretrained(folder/'hf')
    write(folder/'protocol.json',{'kind':'semantic-spec-distill-v1','arm':arm,'context':1024,'codec':'ay_codec.py'if arm=='spec'else'HEX+constant macros',
         'unary_names':UNARY_NAMES,'binary_names':BINARY_NAMES,'actions':ACTIONS,'action_ids':ACTION_IDS,'correct_ids':CORRECT_IDS,
         'neural_headers':{a:header_ids(agent.tokenizer,a)for a in ['write','run','diag']}})
    write(folder/'output-token-ids.json',output_ids(agent.tokenizer))
    write(folder/'manifest.json',{'arm':'asm','output_arm':arm,'quantization_mode':'q4','parameter_count':3022080,'quantization':'Q4 group32 half scales',
         'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
         'selected_step':choice['step'],'selection_used_closed_test':False,
         'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()}})
    write(out/'status.json',{'phase':'complete','selected_step':choice['step']});check_frozen()


def baseline(arm):
    assert(ROOT/'preselected.json').exists();model,tokenizer=load();compact_head(model,output_ids(tokenizer))
    write(ROOT/('source-'+arm+'-closed.json'),evaluate(model,tokenizer,'closed',arm))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','train','audit','baseline']);p.add_argument('--arm',choices=ARMS);a=p.parse_args()
    torch.set_num_threads(4);torch.manual_seed(26110805);torch.backends.cuda.matmul.allow_tf32=False
    if a.action=='prepare':prepare()
    elif a.action=='train':train(a.arm)
    elif a.action=='audit':audit(a.arm)
    else:baseline(a.arm)
