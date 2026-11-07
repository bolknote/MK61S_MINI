"""Full ISA Q4 SFT, balanced commands, real tool failures and protected input rows."""
import argparse
import collections
import fcntl
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import time

import numpy as np
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from full_isa_common import ROOT,ARMS,INITIAL,read,sha,write,allowed,task_prompt,target
from full_isa_protocol import prompt,linear_instructions
from full_isa_eval import development,brief,selection
from codec_train import compact_loss
from codec_common import compact_head
from native_context import wrap
from native_quant import attach,save,packed_copy
from tasks import BUILD


class Course:
    def __init__(self,tokenizer):
        self.tokenizer=tokenizer;self.rng=random.Random(6117070)
        self.rows=read(ROOT/'sft-light.jsonl');self.legacy=read(ROOT/'legacy-light.jsonl');self.repairs=read(ROOT/'repair-examples.jsonl')
        self.catalog={r['code']:r for r in json.loads((ROOT/'catalog.json').read_text())}
        self.pools=collections.defaultdict(list);self.primitives=collections.defaultdict(list)
        for i,row in enumerate(self.rows):
            if row.get('source')=='full_isa_teacher':self.pools['teacher'].append(i)
            elif row['kind']=='primitive':self.primitives[row['opcode']].append(i)
            else:self.pools[row['kind']].append(i)
        assert set(self.primitives)==set(range(256))
        self.documented=[op for op in self.primitives if self.catalog[op]['risk']=='documented']
        self.other=[op for op in self.primitives if self.catalog[op]['risk']!='documented']
        self.domain=[tokenizer.encode(x['text'],add_special_tokens=False)for x in read(BUILD/'training/domain-documents.jsonl')]
        self.domain=[x for x in self.domain if len(x)>=32]
        self.stream=np.memmap(BUILD/'native-mixed-v1/language/train.u16',mode='r',dtype='<u2')
        self.counts=collections.Counter();self.contexts=collections.Counter();self.digest='00'*32

    def encode(self,x,y):
        before=self.tokenizer.encode(x,add_special_tokens=False);after=self.tokenizer.encode(y,add_special_tokens=False)+[self.tokenizer.eos_token_id]
        return before+after,[-100]*len(before)+after

    @lru_cache(maxsize=16000)
    def pair(self,index,kind,context,salt):
        if kind=='legacy':row=self.legacy[index]
        elif kind in ['repair','trace','done']:
            source=self.repairs[index];row={**source}
            if context>512:row['task']=wrap(row['task'],self.tokenizer,context-192,salt)
            if kind=='done':return self.encode(task_prompt(row,initial_code=row['reference_code'],observation='PASS'),'<done/>')
            if kind=='trace':
                row['task']+=' Сначала запроси трассировку текущего кода.'
                return self.encode(task_prompt(row,initial_code=row.get('current_code')or[0x54,0x50],observation=row['observation']),'<trace/>')
            return self.encode(task_prompt(row,initial_code=row.get('current_code'),observation=row.get('trace',row['observation'])if salt%2 else row['observation']),target(row['reference_code']))
        else:row=self.rows[index]
        row={**row}
        if context>512:row['task']=wrap(row['task'],self.tokenizer,context,salt)
        if kind=='plan':
            instructions=linear_instructions(row['reference_code']);steps=[]
            for step in instructions:
                name=self.catalog[step['opcode']]['name']
                if step['operand']is not None:name+=' '+f'{step["operand"]:02X}'
                steps.append(name)
            x='МК-61. Кратко назови последовательность команд для решения.\nУсловие: '+row['task']+'\nПлан: '
            return self.encode(x,'; '.join(steps)+'.')
        return self.encode(task_prompt(row),target(row['reference_code']))

    def pick(self,kind):
        rng=self.rng
        if kind=='primitive':
            op=rng.choice(self.documented if rng.random()<.95 else self.other)
            return rng.choice(self.primitives[op])
        if kind=='legacy':return rng.randrange(len(self.legacy))
        if kind in ['repair','trace','done']:return rng.randrange(len(self.repairs))
        if kind=='teacher'and not self.pools['teacher']:
            return rng.choice(self.pools['numeric_synthesis'])
        if kind=='plan':return rng.randrange(len(self.rows))
        if kind=='game_fragment'and not self.pools[kind]:return rng.choice(self.pools['programming'])
        return rng.choice(self.pools[kind])

    def batch(self,context,step,device):
        rng=self.rng;rows=[];lm=[];draws=[]
        if step<=1000:quotas=[('primitive',64),('numeric_synthesis',24),('programming',8),('interactive_game',2),('teacher',8),('tools',8),('legacy',8)]
        else:quotas=[('primitive',32),('numeric_synthesis',32),('programming',16),('interactive_game',4),('teacher',12),('tools',8),('legacy',18)]
        for category,n in quotas:
            count=0
            while count<n:
                kind=rng.choices(['repair','trace','done'],weights=[.55,.25,.2])[0]if category=='tools'else category
                if category=='programming'and rng.random()<.15:kind='game_fragment'
                index=self.pick(kind);salt=rng.randrange(32);x,y=self.pair(index,kind,context,salt)
                if len(x)>context:self.counts['resampled_overlength']+=1;continue
                rows.append((x,y));lm.append(False);draws.append([kind,index,context,salt]);count+=1
                self.counts['kind:'+kind]+=1
                if category not in ['tools','legacy']:
                    row=self.rows[index];self.counts['group:'+row['group']]+=1
                    if row.get('opcode')is not None:self.counts[f'opcode:{row["opcode"]:02X}']+=1
        # Three language chunks preserve Russian; three supervised command
        # plans teach decomposition using the full Russian head only at training.
        for _ in range(3):
            if rng.random()<.5:
                index=rng.randrange(len(self.domain));source=self.domain[index];start=rng.randrange(max(1,len(source)-511));ids=source[start:start+512];draws.append(['domain',index,start])
            else:
                start=rng.randrange(len(self.stream)-513);ids=self.stream[start:start+512].astype('int64').tolist();draws.append(['language',start])
            rows.append((ids,ids));lm.append(True);self.counts['language']+=1
        count=0
        while count<3:
            index=self.pick('plan');salt=rng.randrange(32);x,y=self.pair(index,'plan',context,salt)
            if len(x)>context:self.counts['resampled_plan']+=1;continue
            rows.append((x,y));lm.append(True);draws.append(['plan',index,context,salt]);self.counts['auxiliary_plan']+=1;count+=1
        assert len(rows)==128
        order=list(range(128));rng.shuffle(order);rows=[rows[i]for i in order];lm=[lm[i]for i in order]
        self.digest=hashlib.sha256(bytes.fromhex(self.digest)+json.dumps([step,context,draws,order],separators=(',',':')).encode()).hexdigest()
        size=max(len(x)for x,y in rows);ids=torch.full((128,size),self.tokenizer.pad_token_id or 0,dtype=torch.long);labels=torch.full_like(ids,-100);mask=torch.zeros_like(ids)
        for i,(x,y)in enumerate(rows):ids[i,:len(x)]=torch.tensor(x);labels[i,:len(y)]=torch.tensor(y);mask[i,:len(x)]=1
        return ids.to(device),mask.to(device),labels.to(device),torch.tensor(lm,dtype=torch.bool,device=device)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args()
    out=ROOT/a.arm;out.mkdir(exist_ok=True);lock=(out/'training.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    prepared=json.loads((ROOT/'prepared.json').read_text());policy=json.loads((ROOT/'policy.json').read_text())
    assert all(sha(ROOT/name)==v for name,v in prepared['files'].items())
    source_names=['full_isa_train.py','full_isa_common.py','full_isa_protocol.py','full_isa_eval.py','full_isa_vm.py','full_isa_bridge.cpp','core_bridge.cpp',
      'codec_train.py','codec_common.py','codec_eval.py','native_quant.py','lowbit.py','quantization.py','native_context.py']
    signature={'arm':a.arm,'prepared_sha256':sha(ROOT/'prepared.json'),'initial_master_sha256':sha(INITIAL/'model.safetensors'),
      'policy_sha256':sha(ROOT/'policy.json'),'steps':policy['steps_each'],'sources':{n:sha(Path(__file__).parent/n)for n in source_names}}
    if(out/'training.json').exists():assert json.loads((out/'training.json').read_text())['signature']==signature;print('Matching full ISA training complete');return
    archive=out/'source';archive.mkdir(exist_ok=True)
    for name in source_names:shutil.copyfile(Path(__file__).parent/name,archive/name)
    torch.set_num_threads(4);torch.manual_seed(6117071);torch.cuda.set_per_process_memory_fraction(policy['memory_fraction_each']);torch.backends.cuda.matmul.allow_tf32=True
    state_path=out/'optimizer/state.pt';state=torch.load(state_path,map_location='cpu',weights_only=True)if state_path.exists()else None
    if state:assert state['signature']==signature
    source=out/'last'if state else INITIAL;tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False).to('cuda');attach(model,'q4')
    embedding=model.get_input_embeddings().parametrizations.weight.original;head=torch.tensor(allowed(),device='cuda')
    row_mask=torch.zeros(embedding.shape[0],dtype=torch.bool,device='cuda');row_mask[head]=True
    protected_reference=embedding.detach()[~row_mask].clone()
    optimizer=torch.optim.AdamW([{'params':[p for p in model.parameters()if p is not embedding],'factor':1.,'weight_decay':policy['weight_decay']},
      {'params':[embedding],'factor':policy['embedding_lr_factor'],'weight_decay':0.}],lr=policy['lr'])
    course=Course(tokenizer);history=[];best=None;best_step=0;first=0
    if state:
        optimizer.load_state_dict(state['optimizer']);course.rng.setstate(state['rng']);torch.set_rng_state(state['torch_rng']);torch.cuda.set_rng_state_all(state['cuda_rng'])
        course.counts.update(state['counts']);course.contexts.update(state['contexts']);course.digest=state['digest'];history=state['history'];best=state['best'];best_step=state['best_step'];first=state['step']
    def validate(step):
        nonlocal best,best_step
        if a.arm=='protected':assert torch.equal(embedding.detach()[~row_mask],protected_reference),'A protected input row changed'
        replica,packed=packed_copy(model,out/'development.mkqb','q4');replica.to('cuda').eval();compact_head(replica,allowed())
        result=development(replica,tokenizer);key=selection(result);record={'step':step,'key':key,'summary':brief(result),'packet':packed};history.append(record)
        write(out/f'development-{step}.json',{'metrics':result,**record})
        if best is None or key>best:best=key;best_step=step;save(model,tokenizer,out/'best','q4')
        print(json.dumps({'development':step,'best_step':best_step,'key':key,'kinds':record['summary']['kinds'],'documented':record['summary']['documented'],'legacy':record['summary']['legacy']}),flush=True);del replica
    if not state:validate(0)
    started=time.monotonic();losses=[];steps=policy['steps_each']
    for step in range(first+1,steps+1):
        context=course.rng.choices(policy['contexts'],weights=policy['context_probabilities'])[0];course.contexts[str(context)]+=1
        model.train();optimizer.zero_grad(set_to_none=True)
        rate=policy['lr']*min(1.,step/policy['warmup_updates'])*(.25+.75*(1+math.cos(math.pi*step/steps))/2)
        for g in optimizer.param_groups:g['lr']=rate*g['factor']
        ids,mask,labels,lm=course.batch(context,step,'cuda')
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,head)
        if not torch.isfinite(loss):raise ValueError('Nonfinite full ISA loss')
        losses.append(float(loss.detach()));loss.backward();del loss,ids,mask,labels,lm
        if a.arm=='protected':embedding.grad.mul_(row_mask[:,None])
        torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
        if step==1 or step%50==0:
            status={'phase':'training','arm':a.arm,'step':step,'steps':steps,'best_step':best_step,'loss':sum(losses[-50:])/len(losses[-50:]),
              'seconds':time.monotonic()-started,'context':context,'counts':dict(course.counts),'sample_plan_digest':course.digest}
            write(out/'status.json',status);print(json.dumps(status),flush=True)
        if step%policy['validation_interval']==0 or step==steps:
            validate(step);save(model,tokenizer,out/'last','q4');state_path.parent.mkdir(exist_ok=True)
            current={'signature':signature,'step':step,'optimizer':optimizer.state_dict(),'rng':course.rng.getstate(),'torch_rng':torch.get_rng_state(),
              'cuda_rng':torch.cuda.get_rng_state_all(),'counts':dict(course.counts),'contexts':dict(course.contexts),'digest':course.digest,'history':history,'best':best,'best_step':best_step}
            tmp=state_path.with_suffix('.tmp');torch.save(current,tmp);tmp.replace(state_path)
    assert all(course.counts[f'opcode:{op:02X}']>0 for op in range(256))
    frozen_rows=hashlib.sha256(embedding.detach()[~row_mask].cpu().contiguous().numpy().tobytes()).hexdigest()
    report={'signature':signature,'completed':True,'steps':steps,'best_step':best_step,'best_key':best,'history':history,
      'counts':dict(course.counts),'contexts':dict(course.contexts),'sample_plan_digest':course.digest,'seconds':time.monotonic()-started,
      'all_256_opcodes_sampled':True,'Q4_from_first_update':True,'output_rows':len(head),'no_seven_operation_ast':True,
      'protected_input_rows_unchanged':a.arm=='protected','unchanged_rows_count':int((~row_mask).sum())if a.arm=='protected'else 0,
      'non_output_embedding_rows_sha256':frozen_rows,'new_audit_used_for_selection':False,
      'actual_examples':128*steps,'initial_write_tag_is_fixed_protocol_framing':False}
    write(out/'training.json',report);write(out/'status.json',{'phase':'complete','step':steps,'best_step':best_step})


if __name__=='__main__':main()
