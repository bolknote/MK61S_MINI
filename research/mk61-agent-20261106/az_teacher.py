"""Verified DeepSeek wording, short queries and literal-table augmentation."""
import collections
import concurrent.futures
from decimal import Decimal
import hashlib
import json
import random
import time
import ay_teacher as old
from az_common import ROOT,PARENT,DEV_NUMBERS,TEST_NUMBERS,rows,read,write,save_rows,sha
from ay_finalize import semantic_key
from ay_codec import compile_spec,encode
from ay_data import CONSTANTS
from ar_spec import equivalent,verify
from full_isa_vm import FullVM
from full_isa_protocol import REGISTERS
from ha_protocol import constants,canonical
from av_deepseek import parse_expression

old.ROOT=ROOT  # Runtime configuration only; the prior source file is unchanged.


def pool_for(text):
    pool=old.pool_for(text)
    for value in constants(text):
        opposite=canonical(-Decimal(value))
        if opposite not in pool:pool.append(opposite)
    return pool


def augment_pool(pool,identity):
    rng=random.Random(int(hashlib.sha256(identity.encode()).hexdigest()[:12],16))
    base=old.pool_for('');extra=list(pool[len(base):])
    for value in ['6.25','14.5']:
        if value not in pool and value not in extra:extra.append(value)
    rng.shuffle(extra);return base+extra


class Client(old.Client):
    def call(self,system,user,schema,name):
        if name=='ay_wordings':
            system+=(' Первую формулировку сделай обычным полным запросом, вторую — кратким запросом пользователя. '
             'У выражения может не быть входных регистров: тогда используй только данные числа, не добавляй R0 или X как аргумент. '
             'Сохраняй числа буквально цифрами: 0.125 не заменяй словами «одна восьмая» или выражением 1/8. '
             'Не заменяй данные числа другими эквивалентными числами или выражениями.')
        if name=='ay_reverse':
            system+=(' Короткие запросы допустимы. Если место результата не указано, это X; '
             'без явного указания записи память не меняется. У чисто числовой задачи нет входных регистров: '
             'числовые литералы нельзя заменять именами регистров.')
        return super().call(system,user,schema,name)


def task_text(question,spec,style):
    question=question.strip()
    if not 3<=len(question)<=350:raise ValueError('QUESTION_LENGTH')
    if style=='short':
        text=question
        for r in spec['writes']:text+=' Результат запиши в '+r+'.'
        return text
    return old.task_text(question,spec)


def allowed_numbers(text,split):
    forbidden=DEV_NUMBERS+TEST_NUMBERS if split=='train'else TEST_NUMBERS if split=='development'else[]
    banned={canonical(abs(Decimal(x)))for x in forbidden}
    return not({canonical(abs(Decimal(x)))for x in constants(text)}&banned)


def prepare_chunk(client,chunk):
    accepted={g['id']:[]for g in chunk};audit=[]
    for attempt in range(3):
        todo=[g for g in chunk if len(accepted[g['id']])<(2 if g['split']=='train'else 1)]
        if not todo:break
        generated=old.wordings(client,todo,attempt);candidates=[];lookup={}
        for g in todo:
            questions=generated.get(g['id'],[])[:2]
            preference=int(hashlib.sha256(g['id'].encode()).hexdigest()[-1],16)%2
            order=[0,1]if g['split']=='train'else[preference,1-preference]
            for i in order:
                if i>=len(questions):continue
                style='full'if i==0 else'short'
                try:text=task_text(questions[i],g['spec'],style)
                except (ValueError,TypeError):continue
                if not allowed_numbers(text,g['split']):continue
                if any(x['task']==text for x in accepted[g['id']]):continue
                identifier=g['id']+f':a{attempt}:p{i}'
                candidates.append({'id':identifier,'task':text,'angle':g['spec']['angle']});lookup[identifier]=(g,text,style)
        verified={}
        for at in range(0,len(candidates),8):verified.update(old.reverse(client,candidates[at:at+8]))
        for item in candidates:
            g,text,style=lookup[item['id']];v=verified.get(item['id']);ok=False;error=None
            try:
                if v is None:raise ValueError('REVERSE_MISSING')
                spec={'X':parse_expression(v['X']),'writes':{r:parse_expression(x)for r,x in v['writes'].items()},'angle':v['angle']}
                if set(spec['writes'])-set(REGISTERS):raise ValueError('REGISTER')
                ok=equivalent(spec,g['spec'],g['checker_inputs']+g['audit_inputs'])['tested_equal']
            except (ValueError,SyntaxError,KeyError,ArithmeticError,TypeError,RecursionError)as e:error=str(e)
            audit.append({'id':item['id'],'task':text,'style':style,'verified':bool(ok),'reverse':v,'error':error})
            needed=2 if g['split']=='train'else 1
            if not ok or len(accepted[g['id']])>=needed or any(x['task']==text for x in accepted[g['id']]):continue
            pool=pool_for(text);layout='default'
            if g['split']=='train'and int(hashlib.sha256(item['id'].encode()).hexdigest()[-1],16)%5<2:
                pool=augment_pool(pool,item['id']);layout='permuted_extra_constants'
            try:body=compile_spec(g['spec'],pool);spec_body=encode(g['spec'],pool)
            except (ValueError,ArithmeticError):continue
            accepted[g['id']].append({**g,'task':text,'pool':pool,'reference_body':body,'spec_body':spec_body,
                'paraphrase':len(accepted[g['id']]),'style':style,'pool_layout':layout,'teacher_reverse_verified':True})
    return accepted,audit


def main():
    assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():print('Teacher corpus already frozen');return
    frozen=read(ROOT/'ast-frozen.json')
    for n,d in frozen['files'].items():assert sha(ROOT/n)==d,n
    assert sha(ROOT/'replay-goals.jsonl')==frozen['replay_sha256']
    client=Client();groups=[g for s in ['train','development','closed']for g in rows(ROOT/(s+'-asts.jsonl'))]
    output={s:[]for s in ['train','development','closed']};audit=[];started=time.monotonic();processed=0
    chunks=[groups[at:at+6]for at in range(0,len(groups),6)]
    with concurrent.futures.ThreadPoolExecutor(4)as executor:
        pending={executor.submit(prepare_chunk,client,c):c for c in chunks}
        for future in concurrent.futures.as_completed(pending):
            accepted,checks=future.result();audit.extend(checks)
            for g in pending[future]:
                variants=accepted[g['id']]
                if len(variants)==(2 if g['split']=='train'else 1):output[g['split']].extend(variants)
            processed+=len(pending[future])
            if processed%30==0 or processed==len(groups):
                status={'processed':processed,'total':len(groups),'rows':{s:len(v)for s,v in output.items()},'seconds':time.monotonic()-started}
                write(ROOT/'teacher-status.json',status);print(json.dumps(status),flush=True)
    # Prior examples are replayed with the new explicit pool, not sent to teacher.
    for g in rows(ROOT/'replay-goals.jsonl'):
        g['pool']=pool_for(g['task']);g['reference_body']=compile_spec(g['spec'],g['pool']);g['spec_body']=encode(g['spec'],g['pool'])
        g['pool_layout']='default';output['train'].append(g)
    # Remove shared signatures and exact question reuse before freezing the new exam.
    prior_seen=set();prior_questions=set()
    for s in ['train','development','closed']:
        for g in rows(PARENT/(s+'-clean.jsonl')):
            prior_seen.add(semantic_key(g['spec']));prior_questions.add((g['spec']['angle'],g['task']))
    seen=set(prior_seen);questions=set(prior_questions);counts={};vm=FullVM();ROM_cases=0
    for split in ['train','development','closed']:
        by_id=collections.defaultdict(list)
        for g in output[split]:by_id[g['id']].append(g)
        kept=[];keys=set();own_questions=set();dropped=collections.Counter()
        for identifier,variants in sorted(by_id.items()):
            replay=variants[0].get('curriculum')=='replay';key=semantic_key(variants[0]['spec'])
            if key in keys or(key in seen and not(split=='train'and replay)):dropped['signature']+=1;continue
            local=set();unique=[]
            for g in variants:
                q=(g['spec']['angle'],g['task'])
                if q in local or q in own_questions or(q in questions and not(split=='train'and replay)):continue
                local.add(q);unique.append(g)
            if not unique:dropped['question']+=1;continue
            keys.add(key);own_questions.update((g['spec']['angle'],g['task'])for g in unique);kept.extend(unique[:2 if split=='train'else 1])
        seen.update(keys);questions.update(own_questions);kept.sort(key=lambda g:(g['id'],g['paraphrase']))
        for g in kept:
            check=verify(vm,g['reference_body'],g['pool'],g['spec'],g['public_inputs']+g['audit_inputs'])
            assert check['status']=='TESTED',(g['id'],check);ROM_cases+=check['cases']
        assert len(kept)>={'train':2700,'development':150,'closed':380}[split],(split,len(kept))
        save_rows(ROOT/(split+'-clean.jsonl'),kept)
        counts[split]={'trees':len(keys),'questions':len(kept),'dropped':dict(dropped),
                      'families':dict(collections.Counter(g['family']for g in kept)),
                      'panels':dict(collections.Counter(g['panel']for g in kept)),
                      'styles':dict(collections.Counter(g.get('style','legacy')for g in kept))}
    save_rows(ROOT/'teacher-reverse-audit.jsonl',audit)
    write(ROOT/'teacher-frozen.json',{'teacher':'deepseek-ai/DeepSeek-V4.1-Flash','counts':counts,'verified_ROM_cases':ROM_cases,
       'files':{s+'-clean.jsonl':sha(ROOT/(s+'-clean.jsonl'))for s in output},'reverse_requests_never_contained_source_AST':True,
       'audit_sha256':sha(ROOT/'teacher-reverse-audit.jsonl'),'prior_exam_questions_never_replayed':True,
       'literal_holdouts_relative_to_training_AST_and_pool':True,'seconds':time.monotonic()-started})
    print(json.dumps({'teacher_complete':True,'counts':counts,'ROM_cases':ROM_cases}),flush=True)


if __name__=='__main__':main()
