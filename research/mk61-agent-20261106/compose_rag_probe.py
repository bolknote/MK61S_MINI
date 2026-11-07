"""Development-only local retrieval experiment; no gradient or hidden answer input."""
import collections
import json
import math
from pathlib import Path
import re
import struct

import torch
from transformers import AutoConfig,AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,read,sha
from course_common import program_prompt,calc_prompt,prefix,answer,parse_prefix
from course_eval import grading_tasks
from emulator import Emulator
from evaluate_batched import generate_many
from harness import extract_code,check_program,close_number
from lowbit import load
from tasks import value_of,registers_used


def main():
    arm='champion';packet=ROOT/'diagnostics/champion-phase2-step6000.mkqb'
    data=packet.read_bytes();n=struct.unpack('<I',data[8:12])[0];c=json.loads(data[12:12+n])['config'];kind=c.pop('model_type')
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_config(AutoConfig.for_model(kind,**c),trust_remote_code=False);load(model,packet);model.to('cuda').eval()
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'initial'/arm,local_files_only=True,trust_remote_code=False)
    corpus=read(ROOT/'course/train.jsonl')+read(ROOT/'phase2-extra-train.jsonl')
    def features(text):
        text=re.sub(r'R[0-3]',' число ',text,flags=re.I)
        return collections.Counter(tokenizer.encode(text.lower(),add_special_tokens=False))
    vectors=[features(t['task'])for t in corpus];df=collections.Counter(k for v in vectors for k in v)
    idf={k:math.log((len(corpus)+1)/(v+1))+1 for k,v in df.items()}
    posting=collections.defaultdict(list);norm=[]
    for i,v in enumerate(vectors):
        w={k:(1+math.log(n))*idf[k]for k,n in v.items()};norm.append(math.sqrt(sum(x*x for x in w.values())))
        for k,x in w.items():posting[k].append((i,x))
    def retrieve(text):
        q=features(text);scores=collections.defaultdict(float)
        for k,count in q.items():
            if k not in idf:continue
            weight=(1+math.log(count))*idf[k]
            for i,x in posting[k]:scores[i]+=weight*x
        count=len(set(re.findall(r'R[0-3]',text)))
        ordered=sorted(scores,key=lambda i:scores[i]/norm[i]if norm[i]else 0.,reverse=True)
        chosen=[];families=set()
        for i in ordered:
            row=corpus[i]
            if len(set(re.findall(r'R[0-3]',row['task'])))!=count:continue
            family=row.get('language_family',row['id'])
            if family in families:continue
            chosen.append(row);families.add(family)
            if len(chosen)==3:break
        return list(reversed(chosen))
    groups={f'manual{level}':read(ROOT/f'development{level}.jsonl')for level in [1,2,3]};results={};em=Emulator()
    for name,raw in groups.items():
        tasks=grading_tasks(raw);rows=[]
        for at in range(0,len(tasks),8):
            batch=tasks[at:at+8];parse_prompts=[];program_prompts=[];demo_ids=[]
            for task in batch:
                demos=retrieve(task['task']);demo_ids.append([r['id']for r in demos])
                p='Учебные примеры. Затем реши только новую задачу.\n'+''.join('Пример: '+r['task']+'\nОтвет: <calc>'+prefix(r['expression'])+'</calc>\n'for r in demos)
                p+='Новая задача.\n'+calc_prompt(task['task']);parse_prompts.append(p)
                p='Учебные примеры. Ответы относятся к примерам. Затем реши только новую задачу.\n'+''.join('Пример: '+r['task']+'\nОтвет: '+answer(r)+'\n'for r in demos)
                p+='Новая задача.\n'+program_prompt(task);program_prompts.append(p)
            assert all(len(tokenizer.encode(x,add_special_tokens=False))+128<=2048 for x in program_prompts+parse_prompts)
            parses=generate_many(model,tokenizer,parse_prompts,plan=False,context=2048,max_new=64)
            programs=generate_many(model,tokenizer,program_prompts,plan=False,context=2048,max_new=128)
            for task,pr,reply,ids in zip(batch,parses,programs,demo_ids):
                m=re.search(r'<calc>(.*?)</calc>',pr,re.S)
                try:
                    expr=parse_prefix(m.group(1))if m else None
                    parsed=expr is not None and registers_used(expr)<=registers_used(task['expression'])and all(close_number(str(value_of(expr,c['registers'])),c['expected_X'])for c in task['public_tests']+task['hidden_tests'])
                except (ValueError,TypeError,ArithmeticError):parsed=False
                code=extract_code(reply);passed=bool(code and'<run/>'in reply and check_program(em,code,task['public_tests']+task['hidden_tests'])['pass'])
                rows.append({'id':task['id'],'parse_pass':parsed,'program_pass':passed,'parse_reply':pr,'reply':reply,'retrieved_training_ids':ids})
        results[name]={'parse_passed':sum(r['parse_pass']for r in rows),'program_passed':sum(r['program_pass']for r in rows),'total':len(rows),'details':rows}
    result={'metrics':results,'source_packet_sha256':sha(packet),'context':2048,'only_training_examples_retrieved':True,
      'retrieval_input':'Only query text; BPE TF-IDF similarity and text-mentioned register count','fresh_opened':False,
      'external_compiler_at_inference':False,'automatic_search':False,'scope':'Local retrieval-assisted neural generation; not pure model accuracy'}
    (ROOT/'diagnostics/rag-champion-phase2-step6000.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{x:v[x]for x in ['parse_passed','program_passed','total']}for k,v in results.items()}),flush=True)


if __name__=='__main__':main()
