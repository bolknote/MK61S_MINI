"""DeepSeek Russian wording, enforced notation filter, independent reverse check."""
import collections
import concurrent.futures
import json
import re
import time
import az_teacher as previous
from ba_common import ROOT,PRIORS,DEV_NUMBERS,TEST_NUMBERS,read,rows,write,save_rows,sha
from ay_finalize import semantic_key
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from ar_spec import verify
from full_isa_vm import FullVM

FUNCTIONS=re.compile(r'\b(?:sin|cos|tan|asin|acos|atan|arcsin|arccos|arctan|sqrt|square|abs|neg|reciprocal|exp|pow10|ln|log10|int|frac|sign|pow|tg|ctg|lg)\b',re.I)
def clean_wording(text):return not FUNCTIONS.search(text)

class Client(previous.Client):
    def call(self,system,user,schema,name):
        if name=='ay_wordings':system+=(' Обязательное требование: НЕ ПИШИ латинские имена функций sin, cos, frac, atan, sqrt, ln и подобные. '
          'Напиши полностью словами по-русски: синус, косинус, дробная часть, арктангенс, квадратный корень, натуральный логарифм. '
          'Латинские буквы разрешены только для регистров R0..RE. Нарушающие это ответы автоматически отбрасываются.')
        return super().call(system,user,schema,name)


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():return
    f=read(ROOT/'ast-frozen.json')
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    previous.old.ROOT=ROOT;previous.DEV_NUMBERS=DEV_NUMBERS;previous.TEST_NUMBERS=TEST_NUMBERS
    original_text=previous.task_text
    def task_text(q,s,style):
        if not clean_wording(q):raise ValueError('EXPLICIT_FUNCTION_NAME')
        return original_text(q,s,style)
    previous.task_text=task_text;previous.augment_pool=lambda p,identity:p
    client=Client();groups=[g for s in ['train','development','closed']for g in rows(ROOT/(s+'-asts.jsonl'))]
    chunks=[groups[i:i+6]for i in range(0,len(groups),6)];output={s:[]for s in ['train','development','closed']};audit=[];processed=0;started=time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(4)as executor:
        pending={executor.submit(previous.prepare_chunk,client,c):c for c in chunks}
        for future in concurrent.futures.as_completed(pending):
            accepted,checks=future.result();audit.extend(checks)
            for g in pending[future]:
                variants=accepted[g['id']]
                if len(variants)==(2 if g['split']=='train'else 1):output[g['split']].extend(variants)
            processed+=len(pending[future])
            if processed%60==0 or processed==len(groups):
                status={'ASTs':processed,'total':len(groups),'rows':{s:len(v)for s,v in output.items()},'seconds':time.monotonic()-started}
                write(ROOT/'teacher-status.json',status);print(json.dumps(status),flush=True)
    for g in rows(ROOT/'replay-goals.jsonl'):
        assert clean_wording(g['task']);g['pool']=pool_for(g['task']);g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode(g['spec'],g['pool'])
        output['train'].append(g)
    prior_questions={(g['spec']['angle'],g['task'])for p in PRIORS for s in ['train','development','closed']for g in rows(p/(s+'-clean.jsonl'))}
    seen=set();counts={};vm=FullVM();ROM_cases=0
    for split,values in output.items():
        grouped=collections.defaultdict(list)
        for g in values:grouped[g['id']].append(g)
        kept=[];own=set()
        for identifier,variants in sorted(grouped.items()):
            unique=[]
            for g in variants:
                q=(g['spec']['angle'],g['task']);allow_old=split=='train'and g.get('curriculum')in ['replay','retired_exam_error']
                if q in seen or q in own or(q in prior_questions and not allow_old):continue
                unique.append(g);own.add(q)
            kept.extend(unique[:2 if split=='train'else 1])
        seen.update(own);kept.sort(key=lambda g:(g['id'],g.get('paraphrase',0)))
        for g in kept:
            assert clean_wording(g['task']);assert g['pool']==pool_for(g['task'])
            check=verify(vm,g['reference_body'],g['pool'],g['spec'],g['public_inputs']+g['audit_inputs'])
            assert check['status']=='TESTED',(g['id'],check);ROM_cases+=check['cases']
        assert len(kept)>={'train':2200,'development':120,'closed':320}[split],(split,len(kept))
        save_rows(ROOT/(split+'-clean.jsonl'),kept)
        counts[split]={'trees':len({g['id']for g in kept}),'questions':len(kept),
            'families':dict(collections.Counter(g['family']for g in kept)),'curriculum':dict(collections.Counter(g.get('curriculum')for g in kept)),
            'styles':dict(collections.Counter(g.get('style','legacy')for g in kept))}
    save_rows(ROOT/'teacher-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'teacher':'DeepSeek-V4.1-Flash','counts':counts,'ROM_cases':ROM_cases,
        'files':{s+'-clean.jsonl':sha(ROOT/(s+'-clean.jsonl'))for s in output},'independent_reverse_no_source_AST':True,
        'all_wordings_pass_explicit_function_name_filter':True,'old_exam_errors_explicitly_retired':True,
        'new_closed_model_generations_seen':False,'seconds':time.monotonic()-started})
    print(json.dumps({'teacher_complete':True,'counts':counts}),flush=True)


if __name__=='__main__':main()
