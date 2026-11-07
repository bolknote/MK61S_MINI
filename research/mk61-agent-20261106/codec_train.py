"""Paired compact-head Q4 SFT; the sampled semantic examples match across formats."""
import argparse
import collections
import fcntl
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import re
import shutil
import time

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from codec_common import ROOT,ARMS,MODES,OLD_VOCAB,read,sha,protocol,allowed_ids,compact_head
from codec_eval import panel,summary,key_for
from compose_common import rename_task,formula_prompt
from compose_semantics import core_labels
from course_common import answer,prefix,program_prompt,calc_prompt
from emulator import Emulator
from harness import check_program,feedback,trace_feedback
from native_context import wrap
from native_quant import attach,save,packed_copy
from tasks import BUILD,program_text


def compact_loss(model,ids,mask,labels,lm_rows,allowed):
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state[:,:-1]
    targets=labels[:,1:];weight=model.get_input_embeddings().weight;losses=[]
    for language in [False,True]:
        batch=torch.nonzero(lm_rows==language).flatten()
        if batch.numel()==0:continue
        rows=torch.arange(OLD_VOCAB,device=ids.device)if language else allowed
        mapping=torch.full((weight.shape[0],),-100,dtype=torch.long,device=ids.device)
        mapping[rows]=torch.arange(len(rows),device=ids.device)
        target=targets.index_select(0,batch);valid=target!=-100
        local=mapping[target.clamp_min(0)];local=torch.where(valid,local,-100)
        if not torch.equal(local!=-100,valid):raise ValueError('A supervised token is outside the compact head')
        logits=F.linear(hidden.index_select(0,batch),weight.index_select(0,rows)).float()
        ce=F.cross_entropy(logits.reshape(-1,len(rows)),local.reshape(-1),ignore_index=-100,reduction='none').reshape_as(local)
        losses.append((ce*valid).sum(1)/valid.sum(1).clamp_min(1))
    return torch.cat(losses).mean()


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(6114510);self.training=read(ROOT/'train.jsonl')
        self.protocols={m:protocol(m)for m in MODES};self.pools=collections.defaultdict(lambda:collections.defaultdict(list));self.pairs=collections.defaultdict(list)
        for i,t in enumerate(self.training):self.pools[t['level']][t['source']].append(i);self.pairs[(t['level'],t['pair_id'])].append(i)
        self.replay=[]
        for row in read(ROOT/'replay.jsonl'):
            prompt=re.sub(r'<plan>.*?</plan>','',row['prompt'],flags=re.S);target=re.sub(r'<plan>.*?</plan>','',row['answer'],flags=re.S)
            self.replay.append(self.encode_pair(prompt,target))
        self.replay_by_context={c:[i for i,pair in enumerate(self.replay)if max(len(value[0])for value in pair.values())<=c]for c in [512,1024,2048]}
        assert all(self.replay_by_context.values())
        self.stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
        self.domain=[tokenizer.encode(r['text'],add_special_tokens=False)for r in read(BUILD/'training/domain-documents.jsonl')]
        self.domain=[x for x in self.domain if len(x)>=32];self.em=Emulator()
        self.counts=collections.Counter();self.contexts=collections.Counter();self.plan_digest='00'*32

    def encode_pair(self,prompt,target,semantic=False):
        result={}
        for mode,p in self.protocols.items():
            x=self.tokenizer.encode(p.encode_text(prompt),add_special_tokens=False);text=p.encode_text(target)
            item=self.tokenizer(text,add_special_tokens=False,return_offsets_mapping=True);y=item['input_ids']+[self.tokenizer.eos_token_id]
            labels=core_labels(item['input_ids'],item['offset_mapping'],6,len(text)-7,self.tokenizer.eos_token_id)if semantic else y
            result[mode]=(x+y,[-100]*len(x)+labels)
        return result

    def choose(self,level):
        sources=sorted(self.pools[level]);weights=[.55 if s=='teacher_new'else .25 if s=='compound_legacy'else .2 if s=='procedural'else .5 for s in sources]
        source=self.rng.choices(sources,weights=weights)[0];return self.rng.choice(self.pools[level][source])

    @lru_cache(maxsize=16384)
    def encoded(self,index,permutation,kind,context,salt):
        row=rename_task(self.training[index],permutation)
        if kind=='compile':return self.encode_pair(formula_prompt(row['expression']),'<write>'+program_text(row['reference_code'])+'</write><run/>')
        wrapping=context-160 if context>512 and kind in ['repair','trace_repair','done']else context
        row['task']=wrap(row['task'],self.tokenizer,wrapping,salt)
        if kind in ['parse','parse_semantic']:return self.encode_pair(calc_prompt(row['task']),'<calc>'+prefix(row['expression'])+'</calc>',kind=='parse_semantic')
        if kind=='program':return self.encode_pair(program_prompt(row),answer(row))
        if kind=='done':return self.encode_pair(program_prompt({**row,'initial_code':row['reference_code']},observation='PASS'),'<done/>')
        wrong=list(row['reference_code']);rng=random.Random(6114511+index);positions=list(range(len(wrong)-1));rng.shuffle(positions)
        for at in positions:
            wrong=list(row['reference_code']);old=wrong[at];pool=[0x60,0x61,0x62,0x63]if 0x60<=old<=0x63 else[0x10,0x11,0x12,0x13,0x31,0x0B,0x22]
            wrong[at]=rng.choice([x for x in pool if x!=old]);checked=check_program(self.em,wrong,row['public_tests'])
            if not checked['pass']:break
        else:return self.encode_pair(program_prompt(row),answer(row))
        observed=trace_feedback(self.em,wrong,row['public_tests'][0])if kind=='trace_repair'else feedback(checked)
        return self.encode_pair(program_prompt({**row,'initial_code':wrong},observation=observed),answer(row))

    def batch(self,mode,context,micro,step,device):
        rng=self.rng;draws=[]
        def quota(fraction):
            value=fraction*micro;return int(value)+(rng.random()<value%1)
        warm=step<=1000
        n_replay=quota(.25);n_lm=min(quota(.1 if warm else .05),micro-n_replay)
        n_basic=min(quota(.15 if warm else .25),micro-n_replay-n_lm);n_comp=micro-n_replay-n_lm-n_basic
        rows=[];languages=[]
        for _ in range(n_replay):
            i=rng.choice(self.replay_by_context[context]);rows.append(self.replay[i][mode]);languages.append(False);draws.append(['replay',i])
        self.counts['formal_tool']+=n_replay
        for _ in range(n_lm):
            if rng.random()<.5:
                i=rng.randrange(len(self.domain));source=self.domain[i];at=rng.randrange(max(1,len(source)-511));ids=source[at:at+512];draws.append(['domain_lm',i,at])
            else:
                at=rng.randrange(len(self.stream)-513);ids=self.stream[at:at+512].astype('int64').tolist();draws.append(['public_lm',at])
            rows.append((ids,ids));languages.append(True)
        self.counts['language']+=n_lm
        kinds=['parse_semantic','parse','program','compile','repair','trace_repair','done'];weights=[.2,.15,.5,.05,.06,.03,.01]
        for category,total in [('simple',n_basic),('composed',n_comp)]:
            group=[]
            while len(group)<total:
                level=1 if category=='simple'else rng.choice([2,3]);i=self.choose(level)
                j=rng.choice(self.pairs[(level,self.training[i]['pair_id'])]);perm=tuple(rng.sample(['R0','R1','R2','R3'],4))
                kind='compile'if warm and category=='composed'else rng.choices(kinds,weights=weights)[0];salt=rng.randrange(32)
                for index in [i,j]:
                    if len(group)>=total:break
                    pair=self.encoded(index,perm,kind,context,salt)
                    # Intersection: neither arm gains extra long examples merely
                    # because its serialized target happens to be shorter.
                    if max(len(x[0])for x in pair.values())>context:
                        self.counts['resampled_overlength_both']+=1;continue
                    group.append(pair[mode]);draws.append(['natural',index,perm,kind,context,salt])
                    self.counts[f'level{level}:{kind}']+=1;self.counts['source:'+self.training[index]['source']]+=1
            self.counts[category]+=len(group);rows+=group;languages += [False]*len(group)
        order=list(range(len(rows)));rng.shuffle(order);rows=[rows[i]for i in order];languages=[languages[i]for i in order]
        assert len(rows)==micro
        fingerprint=json.dumps([step,context,draws,order],separators=(',',':')).encode()
        self.plan_digest=hashlib.sha256(bytes.fromhex(self.plan_digest)+fingerprint).hexdigest()
        length=max(len(x)for x,y in rows);ids=torch.full((micro,length),self.tokenizer.pad_token_id or 0,dtype=torch.long)
        labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for at,(x,y)in enumerate(rows):ids[at,:len(x)]=torch.tensor(x);labels[at,:len(y)]=torch.tensor(y);mask[at,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(languages,dtype=torch.bool,device=device)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);ap.add_argument('--mode',choices=MODES,required=True);a=ap.parse_args()
    out=ROOT/(a.arm+'-'+a.mode);out.mkdir(exist_ok=True);lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    initial=ROOT/'initial'/a.arm/'hf';policy=json.loads((ROOT/'policy.json').read_text());resources=json.loads((ROOT/'resources.json').read_text())
    steps=policy['steps_each'];effective=policy['effective_batch'];source_dir=Path(__file__).parent
    source_names=['codec_train.py','codec_common.py','codec_eval.py','byte_codec.py','compose_common.py','compose_semantics.py',
      'course_common.py','native_quant.py','lowbit.py','quantization.py','native_context.py','harness.py','emulator.py','tasks.py']
    signature={'arm':a.arm,'mode':a.mode,'initial_master_sha256':sha(initial/'model.safetensors'),'frozen_sha256':sha(ROOT/'frozen.json'),
      'resources_sha256':sha(ROOT/'resources.json'),'steps':steps,'effective_batch':effective,'precision':'q4',
      'source_sha256':{name:sha(source_dir/name)for name in source_names}}
    if(out/'training.json').exists():
        assert json.loads((out/'training.json').read_text())['signature']==signature
        print('Matching codec training complete');return
    archive=out/'source';archive.mkdir(exist_ok=True)
    for name in source_names:shutil.copyfile(source_dir/name,archive/name)
    torch.set_num_threads(4);torch.manual_seed(6114512);torch.cuda.set_per_process_memory_fraction(resources['memory_fraction_each'])
    torch.backends.cuda.matmul.allow_tf32=True
    resume=out/'optimizer/state.pt';saved=torch.load(resume,map_location='cpu',weights_only=True)if resume.exists()else None
    if saved:assert saved['signature']==signature
    src=out/'last'if saved else initial
    tokenizer=AutoTokenizer.from_pretrained(src,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(src,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    embedding=model.get_input_embeddings().parametrizations.weight.original
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embedding],'factor':1.},
      {'params':[embedding],'factor':policy['embedding_lr_factor']}],lr=policy['lr'],weight_decay=policy['weight_decay'])
    optimizer_ids={id(p)for g in optimizer.param_groups for p in g['params']}
    course=Course(tokenizer);allowed=torch.tensor(allowed_ids(a.mode),device='cuda');history=[];best=None;best_step=0;start_step=0
    if saved:
        optimizer.load_state_dict(saved['optimizer']);course.rng.setstate(saved['python_rng']);torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state_all(saved['cuda_rng'])
        course.counts.update(saved['counts']);course.contexts.update(saved['contexts']);course.plan_digest=saved['plan_digest']
        history=saved['history'];best=saved['best'];best_step=saved['best_step'];start_step=saved['step']
    def development(step):
        nonlocal best,best_step
        replica,packet=packed_copy(model,out/'development.mkqb','q4');replica.to('cuda').eval();compact_head(replica,allowed_ids(a.mode))
        result=panel(replica,tokenizer,protocol(a.mode));key=key_for(result)
        record={'step':step,'key':key,'summary':summary(result),'packet':packet}
        (out/f'development-{step}.json').write_text(json.dumps({'metrics':result,**record},ensure_ascii=False,indent=2)+'\n');history.append(record)
        if best is None or key>best:best=key;best_step=step;save(model,tokenizer,out/'best','q4')
        assert optimizer_ids=={id(p)for p in model.parameters()}
        print(json.dumps({'development':step,'best_step':best_step,'summary':record['summary']},ensure_ascii=False),flush=True);del replica
    if not saved:development(0)
    started=time.monotonic();losses=[]
    for step in range(start_step+1,steps+1):
        context=course.rng.choices(policy['contexts'],weights=policy['context_probabilities'])[0];course.contexts[str(context)]+=1
        micro=resources['micro_by_context'][str(context)];assert effective%micro==0
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=policy['lr']*min(1.,step/policy['warmup_updates'])*(.25+.75*(1+math.cos(math.pi*step/steps))/2)
        for group in optimizer.param_groups:group['lr']=rate*group['factor']
        value=0.
        for _ in range(effective//micro):
            ids,mask,labels,lm=course.batch(a.mode,context,micro,step,'cuda')
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,allowed)/(effective//micro)
            if not torch.isfinite(loss):raise ValueError('Nonfinite codec QAT loss')
            value+=float(loss.detach());loss.backward();del loss,ids,mask,labels,lm
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step();losses.append(value)
        if step==1 or step%50==0:
            status={'phase':'training','arm':a.arm,'mode':a.mode,'step':step,'steps':steps,'best_step':best_step,
              'loss':sum(losses[-50:])/len(losses[-50:]),'seconds':time.monotonic()-started,'context':context,
              'counts':dict(course.counts),'plan_digest':course.plan_digest}
            (out/'status.json').write_text(json.dumps(status)+'\n');print(json.dumps(status),flush=True)
        if step%1000==0 or step==steps:
            development(step);save(model,tokenizer,out/'last','q4');resume.parent.mkdir(exist_ok=True)
            state={'signature':signature,'step':step,'optimizer':optimizer.state_dict(),'python_rng':course.rng.getstate(),
              'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'counts':dict(course.counts),
              'contexts':dict(course.contexts),'plan_digest':course.plan_digest,'history':history,'best':best,'best_step':best_step}
            temp=resume.with_suffix('.tmp');torch.save(state,temp);temp.replace(resume)
    report={'signature':signature,'completed':True,'steps':steps,'best_step':best_step,'best_key':best,'history':history,
      'actual_sample_counts':dict(course.counts),'optimizer_steps_by_context':dict(course.contexts),'sample_plan_digest':course.plan_digest,
      'seconds':time.monotonic()-started,'target_precision_throughout':'Q4','primary_endpoint':steps,'fresh_used_for_selection':False}
    (out/'training.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','step':steps,'best_step':best_step})+'\n')


if __name__=='__main__':main()
