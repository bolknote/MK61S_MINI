"""Full bounded arithmetic grammar with correct Russian cases and word orders."""
import collections
from concurrent.futures import ThreadPoolExecutor,as_completed
from fractions import Fraction
import hashlib
import json
import random
import re

from compose_balanced import shapes,distinct,wording_key
from compose_common import ROOT,read,make_task,stack_depth,opcount,sha
from course_common import canonical,parse_prefix
from course_teacher import normalize,no_side_effects,TOPICS
from emulator import Emulator,build
from harness import check_program
from tasks import family_of,expression_text,registers_used,split_of,compile_expr,save_jsonl
from teacher_data import call,MODEL

CASES={
 'v':{'n':'значение','a':'значение','g':'значения','d':'значению','i':'значением'},
 '+':{'n':'сумма','a':'сумму','g':'суммы','d':'сумме','i':'суммой'},
 '-':{'n':'разность','a':'разность','g':'разности','d':'разности','i':'разностью'},
 '*':{'n':'произведение','a':'произведение','g':'произведения','d':'произведению','i':'произведением'},
 '/':{'n':'частное','a':'частное','g':'частного','d':'частному','i':'частным'},
 'abs':{'n':'модуль','a':'модуль','g':'модуля','d':'модулю','i':'модулем'},
 'neg':{'n':'результат смены знака','a':'результат смены знака','g':'результата смены знака','d':'результату смены знака','i':'результатом смены знака'},
 'square':{'n':'квадрат','a':'квадрат','g':'квадрата','d':'квадрату','i':'квадратом'}}


def noun(expr,case='a'):
    if isinstance(expr,str):return CASES['v'][case]+' '+expr
    if isinstance(expr,dict):return CASES['neg'][case].split(' смены')[0]+' '+['первого','второго','третьего','четвёртого'][expr['temporary']]+' действия'
    return CASES[expr[0]][case]+' '+' и '.join(noun(x,'g')for x in expr[1:])


def action(expr,variant=0,infinitive=False):
    op,*args=expr;a=args[0];b=args[1]if len(args)>1 else None
    if op=='+':return ('прибавить 'if infinitive else'прибавь ')+noun(a,'a')+' к '+noun(b,'d')if variant%2 else('сложить 'if infinitive else'сложи ')+noun(a,'a')+' с '+noun(b,'i')
    if op=='-':return ('вычесть 'if infinitive else'вычти ')+noun(b,'a')+' из '+noun(a,'g')if variant%2 else'из '+noun(a,'g')+(' вычесть 'if infinitive else' вычти ')+noun(b,'a')
    if op=='*':return noun(a,'a')+(' умножить на 'if infinitive else' умножь на ')+noun(b,'a')if variant%2 else('умножить 'if infinitive else'умножь ')+noun(a,'a')+' на '+noun(b,'a')
    if op=='/':return 'на '+noun(b,'a')+(' разделить 'if infinitive else' раздели ')+noun(a,'a')if variant%2 else('разделить 'if infinitive else'раздели ')+noun(a,'a')+' на '+noun(b,'a')
    if op=='abs':return ('взять модуль 'if infinitive else'возьми модуль ')+noun(a,'g')
    if op=='neg':return 'у '+noun(a,'g')+(' сменить знак'if infinitive else' смени знак')
    return noun(a,'a')+(' возвести в квадрат'if infinitive else' возведи в квадрат')


def steps(expr):
    result=[]
    def visit(x):
        if isinstance(x,str):return x
        args=[visit(y)for y in x[1:]];result.append(action([x[0],*args],len(result)%2))
        return {'temporary':len(result)-1}
    visit(expr)
    return '. '.join(('Сначала 'if i==0 else'Затем ')+text for i,text in enumerate(result))+'. Итог последнего действия нужен в X.'


def cap(text):return text[:1].upper()+text[1:]


def variants(expr):
    return ['Найди '+noun(expr,'a')+'.','Вычисли '+noun(expr,'a')+'.',
      cap(action(expr))+'.',cap(action(expr,1))+'.',
      'Какой получится результат, если '+action(expr,0,True)+'?',
      'Требуется '+noun(expr,'n')+'. Исходные числа уже заданы.',
      'В X нужен результат вычисления '+noun(expr,'g')+'.',steps(expr)]


def exact_value(expr,registers):
    if isinstance(expr,str):return registers[expr]
    op,*children=expr;xs=[exact_value(x,registers)for x in children];a=xs[0]
    if op=='abs':return abs(a)
    if op=='neg':return-a
    if op=='square':return a*a
    b=xs[1]
    return a+b if op=='+'else a-b if op=='-'else a*b if op=='*'else a/b


def equivalent(expected,parsed):
    if canonical(expected)==canonical(parsed):return True
    if opcount(parsed)>6 or not registers_used(parsed)<=registers_used(expected):return False
    rng=random.Random(6113601);checked=0
    for _ in range(160):
        values={r:Fraction(rng.choice([-19,-7,-3,-1,0,1,2,5,13]),rng.choice([1,1,2,3]))for r in sorted(registers_used(expected))}
        try:left=exact_value(expected,values)
        except ArithmeticError:continue
        try:right=exact_value(parsed,values)
        except ArithmeticError:return False
        if left!=right:return False
        checked+=1
    return checked>=64


def main():
    out=ROOT/'morphology-phase4';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():return
    rng=random.Random(6113602);em=Emulator(build(out/'libmorph-reference.so'))
    forbidden={normalize(t['task'])for name in ['fresh1','fresh2','fresh3','development1','development2','development3']for t in read(ROOT/(name+'.jsonl'))}
    forbidden.update(normalize(t['task'])for s in ['validation','test']for t in read(ROOT/f'course/{s}.jsonl'))
    bank={};candidates=[]
    for level in [1,2,3]:
        for skeleton in shapes(level):
            family=family_of(skeleton)
            if family in bank:continue
            expr=distinct(skeleton,rng.sample(['R0','R1','R2','R3'],4))
            if stack_depth(expr)>4 or(level>1 and len(registers_used(expr))<2):continue
            try:base=make_task('',expr,rng,'morph:'+hashlib.sha256(family.encode()).hexdigest()[:18],split='train',emulator=em)
            except ValueError:continue
            bank[family]=base
            for style,text in enumerate(variants(expr)):
                if normalize(text)in forbidden:continue
                candidates.append({**base,'id':base['id']+f':grammar{style}','task':text,'source':'morphological',
                   'origin':'correct_case_and_word_order','pair_id':base['id'],'language_family':base['id'],'style':style})
    # Additional controlled-language structural test; never a teacher prompt.
    probe=ROOT/'fresh4-structure.jsonl'
    if not probe.exists():
        rows=[];seen=set();pool=list(shapes(4));rng.shuffle(pool)
        for skeleton in pool:
            def count(x):return 1 if isinstance(x,str)else sum(count(y)for y in x[1:])
            if count(skeleton)!=4:continue
            expr=distinct(skeleton,rng.sample(['R0','R1','R2','R3'],4));family=family_of(expr)
            if family in seen or split_of(expr)!='test'or stack_depth(expr)>4:continue
            try:t=make_task(cap(action(expr,1))+'.',expr,rng,'structural4:'+str(len(rows)),split='fresh4',emulator=em)
            except ValueError:continue
            rows.append(t);seen.add(family)
            if len(rows)==64:break
        assert len(rows)==64;save_jsonl(probe,rows)
        (ROOT/'frozen-structural4.json').write_text(json.dumps({'rows':64,'sha256':sha(probe),'before_phase4_gradients':True,
          'controlled_russian_not_independent_human_stories':True,'whole_expression_structures_not_added_to_training':True},indent=2)+'\n')
    groups=collections.defaultdict(list);jobs=[]
    for row in bank.values():groups[(row['level'],len(registers_used(row['expression'])))].append(row)
    for (level,count),rows in groups.items():
        rng.shuffle(rows)
        if level==1:
            for row in rows:
                for topic in TOPICS[row['expression'][0]].split(';')[:12]:jobs.append((row,topic))
        else:jobs += [(row,'простая практическая история с вопросом')for row in rows[:48]]
    def generate(job):
        row,topic=job;identity=hashlib.sha256((row['id']+':'+topic).encode()).hexdigest()[:20]
        system=('Напиши два разных коротких русских условия для одного выражения. Ответ JSON-массив из двух строк. '
          'Каждое условие задаёт ровно это вычисление. По8-45 слов. Объясни роли всех нужных R0,R1,R2,R3. '
          'Используй естественные падежи и разный порядок упоминания величин. '
          'Не добавляй операции, константы, регистры, округление или изменения исходных регистров. '
          'Не пиши формулу, код, решение или пример значений. Итог нужен в X.')
        values=call(out,'human-style',identity,[{'role':'system','content':system},{'role':'user','content':
          'Выражение: '+expression_text(row['expression'])+'\nСмысл: '+noun(row['expression'],'n')+'\nТема: '+topic}],tokens=1000,temperature=.65)
        result=[]
        for i,text in enumerate(values if isinstance(values,list)else[]):
            if not isinstance(text,str):continue
            text=re.sub(r'Р([0-3])',r'R\1',text).strip()
            if not 6<=len(text.split())<=60 or any(c in text for c in '<>=`')or not no_side_effects(text):continue
            if set(re.findall(r'R[0-9A-F]',text))!=registers_used(row['expression'])or normalize(text)in forbidden:continue
            result.append({**row,'id':row['id']+':human'+identity+':'+str(i),'task':text,'source':'teacher_morph',
              'origin':'teacher_new_cases_and_topics','pair_id':row['id'],'language_family':row['id'],'style':'human'})
        return result
    errors=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        for i,f in enumerate(as_completed([executor.submit(generate,job)for job in jobs]),1):
            try:candidates+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if i%10==0:(out/'status.json').write_text(json.dumps({'phase':'human_generation','done':i,'total':len(jobs),'candidates':len(candidates)})+'\n')
    candidates.sort(key=lambda r:r['id']);rng.shuffle(candidates);batches=[candidates[i:i+10]for i in range(0,len(candidates),10)]
    def verify(index,rows):
        opaque={hashlib.sha256(('morph-blind:'+r['id']).encode()).hexdigest()[:20]:r for r in rows}
        system=('Независимо выведи вычисление из каждого условия. Ответ JSON-массив {"id":"...","prefix":"..."}. '
          'Префикс: операция перед аргументами без скобок. + - * / имеют два аргумента; abs neg square один. '
          'Листья R0,R1,R2,R3. При неоднозначности, неполных ролях, лишних действиях или новых константах верни null. '
          'Все строки независимы; id не содержит ответа.')
        identity=str(index)+'-'+hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()[:12]
        values=call(out,'blind',identity,[{'role':'system','content':system},{'role':'user','content':json.dumps([
          {'id':key,'text':row['task']}for key,row in opaque.items()],ensure_ascii=False)}],tokens=2200,temperature=0)
        decoded={v.get('id'):v.get('prefix')for v in values if isinstance(v,dict)};result=[]
        for key,row in opaque.items():
            try:parsed=parse_prefix(decoded.get(key,''));correct=equivalent(row['expression'],parsed)
            except (ValueError,TypeError,AttributeError):correct=False
            if correct:result.append({**row,'independent_reading':parsed})
        return result
    verified=[]
    with ThreadPoolExecutor(max_workers=4)as executor:
        for i,f in enumerate(as_completed([executor.submit(verify,i,rows)for i,rows in enumerate(batches)]),1):
            try:verified+=f.result()
            except Exception as e:errors.append(str(e)[:200])
            if i%10==0:(out/'status.json').write_text(json.dumps({'phase':'blind_reading','done':i,'total':len(batches),'verified':len(verified)})+'\n')
    seen=set();good=[];rejected=collections.Counter()
    for row in verified:
        if normalize(row['task'])in forbidden:continue
        key=wording_key(row['task'])
        if key in seen:continue
        parsed=row['independent_reading']
        if stack_depth(parsed)>4 or not check_program(em,compile_expr(parsed)+[0x50],row['public_tests']+row['hidden_tests'])['pass']:
            rejected['inverse_does_not_execute_like_reference']+=1;continue
        good.append(row);seen.add(key)
    if len(good)<1500:raise ValueError('Not enough independently read correct-case conditions')
    carried=read(ROOT/'phase3-extra-train.jsonl');combined=carried+good
    state=json.loads((ROOT/'status.json').read_text());assert state.get('course_phase',0)<4 and not(ROOT/'preselected.json').exists()
    target=ROOT/'phase4-extra-train.jsonl';temp=target.with_suffix('.tmp');save_jsonl(temp,combined);temp.replace(target)
    report={'rows':len(combined),'new_verified_rows':len(good),'carried_rows':len(carried),'families':len(bank),'candidate_rows':len(candidates),
      'new_by_level':dict(collections.Counter(x['level']for x in good)),'new_by_source':dict(collections.Counter(x['source']for x in good)),
      'new_by_style':dict(collections.Counter(str(x['style'])for x in good)),
      'rejected':dict(rejected),'errors':errors,'structural_family_policy':'All1/2/3-operation structures',
      'primary_audit_now_tests':'New wordings of known bounded mathematical structures',
      'manual_or_fresh_wordings_used_as_targets':False,'independent_inverse':'Exact AST or160 rational trials with>=64 valid cases plus actual MK61 execution',
      'gradient_targets_sha256':sha(target),'teacher':MODEL}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    (out/'status.json').write_text(json.dumps({'phase':'complete','rows':len(combined)})+'\n');print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
