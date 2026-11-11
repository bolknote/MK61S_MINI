"""Preserve clear natural wording; minimal repairs plus blind ambiguity checks."""
import collections
import concurrent.futures
import copy
import difflib
import hashlib
import json
import re
import threading
import time
import urllib.request
from bl_common import ROOT,read,write,rows,save_rows,sha,signature
from bh_spec import install,equal_spec
from az_teacher import pool_for
from ay_codec import compile_spec,encode
from av_deepseek import parse_expression
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from ar_spec import verify
from ha_protocol import assemble

URL='http://127.0.0.1:18085/v1/chat/completions';MODEL='deepseek-ai/DeepSeek-V4.1-Flash'
STYLES=['короткий разговорный вопрос к калькулятору','обычная математическая фраза',
    'пошаговая просьба с ясными словами «сначала», «затем», «полученный результат»',
    'просьба составить программу для МК-61','лаконичное условие без стандартной вводной фразы',
    'естественная фраза с обратным порядком упоминания основания и показателя, если есть степень',
    'обычный вопрос со словами «единица», «ноль» или «десять», когда соответствующий литерал действительно есть',
    'русское описание числителя и знаменателя, если есть деление']

class Client:
    def __init__(self):
        self.cache=ROOT/'teacher-cache';self.cache.mkdir(exist_ok=True);self.locks={};self.guard=threading.Lock()
    def call(self,system,user,schema,name,seed=261112112):
        payload={'model':MODEL,'messages':[{'role':'system','content':system},{'role':'user','content':json.dumps(user,ensure_ascii=False)}],
            'temperature':0,'seed':seed,'max_tokens':5500,'chat_template_kwargs':{'thinking':False,'enable_thinking':False},
            'response_format':{'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':schema}}}
        data=json.dumps(payload,ensure_ascii=False,sort_keys=True).encode();path=self.cache/(hashlib.sha256(data).hexdigest()+'.json')
        with self.guard:lock=self.locks.setdefault(str(path),threading.Lock())
        with lock:
            if path.exists():cached=read(path)
            else:
                started=time.monotonic()
                for attempt in range(4):
                    try:
                        request=urllib.request.Request(URL,data,headers={'Content-Type':'application/json'})
                        with urllib.request.urlopen(request,timeout=180)as stream:response=json.load(stream)
                        break
                    except Exception:
                        if attempt==3:raise
                        time.sleep(2+attempt)
                cached={'payload':payload,'response':response,'seconds':time.monotonic()-started};write(path,cached)
            text=cached['response']['choices'][0]['message'].get('content')or''
            try:return json.loads(text)['items']
            except (ValueError,KeyError,TypeError):return []

def schema(properties):
    return {'type':'object','properties':{'items':{'type':'array','items':{'type':'object','properties':properties,
        'required':list(properties),'additionalProperties':False}}},'required':['items'],'additionalProperties':False}

def generated(client,goals,attempt):
    props={'id':{'type':'string'},'questions':{'type':'array','items':{'type':'string'},'minItems':2,'maxItems':2}}
    system=('Создай по две РАЗНЫЕ естественные русские формулировки полной задачи. Это обычные запросы к калькулятору, '
        'не искусственная грамматика и не пересказ AST. Дерево задано префиксным JSON: [операция, аргументы]. '
        'Сохраняй все операции, литералы, регистры, порядок деления/вычитания и основание/показатель. '
        'Скобки добавляй только там, где иначе появятся два прочтения; можно объяснить порядок обычными словами. '
        'Если past_misread задана, маленькая модель так ошибочно поняла условие; сформулируй тот же правильный смысл обычными словами с ясной областью операций. '
        'Не превращай всё в «Вычисли: функция (...)», не добавляй одинаковый служебный хвост. '
        'Вопрос без адреса записи означает X и сохранение памяти. Если writes непустой, явно попроси записать тот же результат в данный регистр. '
        'Режим angle уже задан калькулятором; не придумывай другой. Регистры R0..RE, допускается пробел R B. '
        'Числа пиши цифрами с точкой, кроме естественных слов для0,1,2,10; не заменяй литерал новым выражением. '
        'Функции пиши по-русски, без sin/ln/frac и HEX. int — отсечение к нулю, frac — дробная часть с исходным знаком; знак0 равен0. '
        'Старайся укладываться в350 символов. Возвращай все id и только JSON items.')
    values=[]
    for g in goals:
        h=int(hashlib.sha256(g['id'].encode()).hexdigest()[:8],16)
        values.append({'id':g['id'],'past_misread':g.get('past_misread'),'X':g['spec']['X'],'writes':list(g['spec']['writes']),'angle':g['spec']['angle'],
            'styles':[STYLES[(h+attempt)%len(STYLES)],STYLES[(h+attempt+3)%len(STYLES)]]})
    return {x['id']:x.get('questions',[])for x in client.call(system,values,schema(props),'bl_natural_wordings')}

def reviewed(client,candidates,second=False):
    props={'id':{'type':'string'},'clear':{'type':'boolean'},'X':{'type':'string'},
        'stores':{'type':'array','items':{'type':'string','enum':REGISTERS},'maxItems':1},
        'angle':{'type':'string','enum':['DEG','RAD','GRAD']},'alternative':{'type':'string'},'reason':{'type':'string'}}
    system=('Проверь ТОЛЬКО русское условие, не предполагая никакого эталонного ответа. '
        'Восстанови математический смысл: X — выражение через исходные R0..RE, stores — явно запрошенная запись того же результата, angle — данный режим. '
        'Записи нет по умолчанию, результат X. R B означает RB. Допустимы числа,pi,+,-,*,/,**,скобки и функции '
        'sin,cos,tan,asin,acos,atan,sqrt,square,reciprocal,abs,neg,exp,pow10,ln,log10,int,frac,sign. '
        'Не вычисляй выражение до готового числа: сохрани запрошенные операции. int отсекает к нулю, frac сохраняет знак, sign(0)=0. '
        'Отдельно проверь неоднозначность: границу аргумента функции, порядок деления, область степени и запись памяти. '
        'clear=true только если есть одно разумное чтение. alternative — второе выражение только при действительной языковой неоднозначности, иначе пустая строка. '
        'Не выдумывай альтернативу с добавленными/потерянными словами или операциями. '
        'Каждое условие самодостаточно: не дополняй его сведениями из других элементов списка. '
        'Например «логарифм от R2 умножить на5» требует уточнения области аргумента; '
        '«найди логарифм R2, затем умножь результат на5» яснее, но основание логарифма всё равно нужно назвать. '
        'reason — очень коротко, без рассуждения. Верни все id и только JSON items.')
    if second:system+=' Это повторная независимая подача: особенно внимательно проверь возможное присоединение оборотов, а не угадывай намерение автора.'
    # Hide semantic/family IDs and never place sibling paraphrases in one review:
    # an incomplete question must not inherit meaning from its better sibling.
    groups=[]
    for c in candidates:
        for group in groups:
            if all(signature(x['goal']['spec'])!=signature(c['goal']['spec'])for x in group):group.append(c);break
        else:groups.append([c])
    result={}
    for group in groups:
        identities={'q'+hashlib.sha256((c['id']+str(second)).encode()).hexdigest()[:14]:c for c in group}
        values=[{'id':key,'task':c['text'],'angle':c['goal']['spec']['angle']}for key,c in sorted(identities.items())]
        for item in client.call(system,values,schema(props),'bl_blind_review_B'if second else'bl_blind_review_A',261112113 if second else 261112112):
            c=identities.get(item.get('id'))
            if c:result[c['id']]={**item,'id':c['id']}
    return result

def parsed(review):
    expr=parse_expression(review['X']);return {'X':expr,'writes':{r:expr for r in review['stores']},'angle':review['angle']}

def scope_warnings(text):
    # Flags only concrete risky wording; it neither chooses an interpretation nor
    # rewrites a clear task into the controlled grammar from the previous round.
    out=[];plain=text
    while re.search(r'\([^()]*\)',plain):plain=re.sub(r'\([^()]*\)',' [BOUND] ',plain)
    atom=r'(?:R\s*[0-9A-E]|-?\d+(?:\.\d+)?)'
    head=r'(?:синус[а-я]*|косинус[а-я]*|тангенс[а-я]*|логарифм[а-я]*|квадрат(?:а|у|ом)?|модул[ьяею]|знак[а-я]*|корень|корня|дробн[а-я]+ часть|цел[а-я]+ часть|обратн[а-я]+ величин[а-я]*)'
    if re.search(head+r'\s+(?:от\s+)?(?:(?:числа|значения|выражения|регистра)\s+)?'+atom+r'\s+(?:плюс|минус|умножить|разделить|в степени)\b',plain,re.I):
        out.append('UNMARKED_FUNCTION_ARGUMENT_BOUNDARY')
    if re.search(r',\s*возвед[её]нн[а-я]*\s+в степень',plain,re.I):out.append('POWER_PARTICIPLE_ATTACHMENT')
    if re.search(r'возвед[её]н[а-я]*\s+в степень\s+с основанием',plain,re.I):out.append('MIXED_POWER_BASE_AND_EXPONENT')
    if re.search(r'дел(?:ить|[её]нн[а-я]*)[^.!?;]*\s+и минус\b',plain,re.I):out.append('DIVISION_AND_MINUS_BOUNDARY')
    return out

def acceptable(c,review):
    try:
        if not review or not review['clear']or scope_warnings(c['text']) or re.search(r'JSON|items|AST|local_scope_warnings',c['text'],re.I):return False
        if not equal_spec(parsed(review),c['goal']['spec']):return False
        if review['alternative'].strip():
            alt={**parsed(review),'X':parse_expression(review['alternative'])}
            if not equal_spec(alt,c['goal']['spec']):return False
        pool=pool_for(c['text']);encode(c['goal']['spec'],pool)
        return 3<=len(c['text'])<=650 and not re.search(r'\b(?:sin|cos|tan|asin|acos|atan|sqrt|square|ln|log10|frac|reciprocal|pow10)\b',c['text'],re.I)
    except (ValueError,KeyError,TypeError,SyntaxError,ArithmeticError):return False

def repaired(client,candidates,reasons,attempt):
    props={'id':{'type':'string'},'task':{'type':'string'}}
    system=('Точечно исправь русскую формулировку, чтобы она ясно задавала приложенный смысл. '
        'Сохрани исходный стиль, короткие слова и порядок повествования. Меняй только ошибочный или двусмысленный фрагмент. '
        'Не переписывай весь запрос в шаблон и не заменяй его формулой. Для области аргумента можно добавить слова или пару скобок. '
        'Не добавляй новые числовые литералы; десятичные числа пиши с точкой. В X-дереве [операция, аргументы], '
        'writes содержит адрес записи того же результата. Не пиши код МК-61, английские имена функций или AST в самом тексте. '
        'Если указаны local_scope_warnings, обязательно устрани ровно эти риски: явно обозначь границу аргумента '
        'или раздели действия словом «затем», даже если авторское намерение кажется очевидным. '
        'Если вопрос и так ясен, точен и local_scope_warnings пуст, верни его без изменений. Только JSON items.')
    values=[{'id':c['id'],'task':c['text'],'required_spec':c['goal']['spec'],'issue':reasons.get(c['id']),
        'local_scope_warnings':scope_warnings(c['text']),'attempt':attempt}for c in candidates]
    return {x['id']:x['task'].strip()for x in client.call(system,values,schema(props),'bl_minimal_edit')}

def check_candidates(client,candidates,dual):
    accepted=[];audit=[];pending=list(candidates)
    for attempt in range(3):
        if not pending:break
        first=reviewed(client,pending);survivors=[c for c in pending if acceptable(c,first.get(c['id']))]
        second=reviewed(client,survivors,True)if dual and survivors else{}
        failures=[];reasons={}
        for c in pending:
            ok=acceptable(c,first.get(c['id']))and(not dual or acceptable(c,second.get(c['id'])))
            audit.append({'id':c['id'],'text':c['text'],'original':c['original'],'source':c['source'],'attempt':attempt,
                'review_A':first.get(c['id']),'review_B':second.get(c['id']),'accepted':ok,
                'source_AST_absent_from_review':True,'local_scope_warnings':scope_warnings(c['text'])})
            if ok:accepted.append(c)
            else:failures.append(c);reasons[c['id']]={'A':first.get(c['id']),'B':second.get(c['id'])}
        if attempt==2 or not failures:break
        fixes=repaired(client,failures,reasons,attempt);pending=[]
        for c in failures:
            text=fixes.get(c['id'],'')
            if text==c['text']or not 3<=len(text)<=650:continue
            if difflib.SequenceMatcher(None,c['original'],text,autojunk=False).ratio()<.60:continue
            pending.append({**c,'text':text,'edited':True})
    return accepted,audit

def chunk(client,goals):
    result={g['id']:[]for g in goals};audit=[]
    old=[]
    for g in goals:
        for i,q in enumerate(g.get('original_questions',[])[:2]):old.append({'id':g['id']+f':old:{i}','goal':g,'text':q.strip(),'original':q.strip(),'source':'old','edited':False})
    if old:
        # Reuse the previously frozen, validated corpus; remove known metadata leaks.
        if goals[0]['split']=='train' and all(g.get('curriculum')!='new_minimal' for g in goals):
            accepted=[c for c in old if not re.search(r'JSON|items|AST|local_scope_warnings',c['text'],re.I)]
            checks=[{'id':c['id'],'text':c['text'],'accepted':True,'reused_previous_frozen_wording':True}for c in accepted]
        else:accepted,checks=check_candidates(client,old,False)
        audit.extend(checks)
        for c in accepted:result[c['goal']['id']].append(c)
    def needed(g):return (2 if g.get('curriculum')=='own_error_variant' or not g.get('original_questions') else 1)if g['split']=='train'else 1
    for attempt in range(3):
        todo=[g for g in goals if len(result[g['id']])<needed(g)]
        if not todo:break
        variants=generated(client,todo,attempt);candidates=[]
        for g in todo:
            for i,q in enumerate(variants.get(g['id'],[])[:2]):
                q=q.strip()
                if q and all(c['text']!=q for c in result[g['id']]):
                    candidates.append({'id':g['id']+f':new:{attempt}:{i}','goal':g,'text':q,'original':q,'source':'new','edited':False})
        # Bound review batches independently from generation batches.
        for at in range(0,len(candidates),8):
            accepted,checks=check_candidates(client,candidates[at:at+8],goals[0]['split']!='train' or any(g.get('curriculum')=='own_error_variant' for g in goals));audit.extend(checks)
            for c in accepted:
                key=c['goal']['id'];needed_count=needed(c['goal'])
                if len(result[key])<needed_count and all(x['text']!=c['text']for x in result[key]):result[key].append(c)
    return result,audit

def main():
    install();assert not(ROOT/'frozen.json').exists()
    if(ROOT/'teacher-frozen.json').exists():return
    bank=read(ROOT/'ast-frozen.json')
    for n,d in bank['files'].items():assert sha(ROOT/n)==d,n
    client=Client();output={s:[]for s in ['train','development','closed']};checks=[];processed=0;last_reported=0;started=time.monotonic()
    batches=[]
    for split in output:
        groups=rows(ROOT/(split+'-asts.jsonl'));batches.extend(groups[i:i+4]for i in range(0,len(groups),4))
    total=sum(len(x)for x in batches)
    with concurrent.futures.ThreadPoolExecutor(16)as pool:
        pending={pool.submit(chunk,client,goals):goals for goals in batches}
        for future in concurrent.futures.as_completed(pending):
            accepted,audit=future.result();checks.extend(audit)
            for g in pending[future]:
                if not accepted[g['id']]:continue
                for i,c in enumerate(accepted[g['id']]):
                    pool_values=pool_for(c['text']);row={**g,'task':c['text'],'pool':pool_values,
                        'reference_body':compile_spec(g['spec'],pool_values),'spec_body':encode(g['spec'],pool_values),
                        'style':'natural','paraphrase':i,'wording_source':c['source'],'point_edited':c['edited'],
                        'original_wording':c['original'],'blind_ambiguity_checked':True,'dual_blind_checked':g['split']!='train' or g.get('curriculum')=='own_error_variant'}
                    row.pop('original_questions',None);output[g['split']].append(row)
            processed+=len(pending[future])
            if processed//20>last_reported//20 or processed==total:
                last_reported=processed
                status={'ASTs':processed,'total':total,'accepted':{s:len(v)for s,v in output.items()},'seconds':round(time.monotonic()-started,1)}
                write(ROOT/'teacher-status.json',status);print(json.dumps(status),flush=True)
    source_goals={g['id']:g for s in output for g in rows(ROOT/(s+'-asts.jsonl'))}
    for s in ['development','closed']:
        for kind in ['editorial','structured']:
            source_goals.update({g['id']:g for g in rows(ROOT/(s+'-'+kind+'.jsonl'))})
    counts={};all_signatures=set();all_questions=set();ROM=0;verified_ids=set();byte_checks=0
    from be_language import question
    for split in output:
        for g in (rows(ROOT/(split+'-editorial.jsonl'))if split!='train'else[]):
            # Editorial probes have independent predefined wording and exact hand-authored formulas.
            g={**g,'wording_source':'editorial','point_edited':False,'blind_ambiguity_checked':False,'dual_blind_checked':False}
            output[split].append(g)
        if split!='train':
            for i,g in enumerate(rows(ROOT/(split+'-structured.jsonl'))):
                q=question(g['spec'],['bracket','named','chain'][i%3],g['id']);p=pool_for(q)
                output[split].append({**g,'task':q,'pool':p,'reference_body':compile_spec(g['spec'],p),'spec_body':encode(g['spec'],p),
                    'style':'structured','wording_source':'structured','point_edited':False})
        kept=[];local=set()
        for g in sorted(output[split],key=lambda x:(x['id'],x.get('paraphrase',0))):
            key=signature(g['spec']);q=(g['spec']['angle'],g['task'])
            if key in all_signatures or q in all_questions or q in local:continue
            local.add(q);kept.append(g)
        keys={signature(g['spec'])for g in kept};all_signatures|=keys;all_questions|=local
        for g in kept:
            source=source_goals[g['id']]
            assert assemble(g['reference_body'],g['pool'],'asm')==assemble(source['reference_body'],source['pool'],'asm'),g['id']
            byte_checks+=1
            if g['id']not in verified_ids:
                ROM+=len(source['public_inputs'])+len(source['checker_inputs'])+len(source['audit_inputs']);verified_ids.add(g['id'])
        assert len(kept)>={'train':7500,'development':350,'closed':900}[split],(split,len(kept))
        save_rows(ROOT/(split+'-clean.jsonl'),kept)
        counts[split]={'trees':len(keys),'questions':len(kept),'panels':dict(collections.Counter(g['panel']for g in kept)),
            'wording_sources':dict(collections.Counter(g['wording_source']for g in kept)),
            'original_kept_exactly':sum(g['wording_source']=='old'and not g['point_edited']for g in kept),
            'old_point_edited':sum(g['wording_source']=='old'and g['point_edited']for g in kept),
            'new_point_edited':sum(g['wording_source']=='new'and g['point_edited']for g in kept)}
    save_rows(ROOT/'teacher-audit.jsonl',checks)
    write(ROOT/'teacher-frozen.json',{'teacher':MODEL,'counts':counts,'source_ROM_cases':ROM,'reference_program_byte_checks':byte_checks,
        'ROM_validation_reused_from_frozen_AST_generation':True,
        'files':{s+'-clean.jsonl':sha(ROOT/(s+'-clean.jsonl'))for s in output},'audit_sha256':sha(ROOT/'teacher-audit.jsonl'),
        'clear_original_wording_preserved':True,'minimal_edit_similarity_floor':.60,
        'blind_reviews_no_source_AST':True,'two_blind_prompts_for_generated_evaluation':True,
        'opaque_review_ids':True,'sibling_paraphrases_never_reviewed_together':True,
        'same_teacher_model_not_independent_human_validation':True,'closed_model_generations_seen':False,'SGD_started':False,
        'seconds':time.monotonic()-started})
    print(json.dumps({'natural_data_ready':True,'counts':counts}),flush=True)

if __name__=='__main__':main()
