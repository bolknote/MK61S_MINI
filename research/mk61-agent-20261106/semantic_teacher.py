"""New contrastive conditions plus blinded teacher role/step annotations."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import collections
import hashlib
import json
import random
import re
import time

from semantic_common import ROOT,write_json,read,sha
from compose_balanced import shapes,distinct,wording_key
from compose_common import make_task,opcount,stack_depth
from course_common import ARITY,canonical,parse_prefix,prefix
from course_teacher import no_side_effects
from emulator import Emulator,build
from tasks import BUILD,save_jsonl,registers_used,expression_text
import teacher_data

teacher_data.URL='http://127.0.0.1:8001/v1/chat/completions'
STYLES=[
 'Естественная просьба с понятными ролями чисел; не называй арифметические действия, если они понятны из сюжета.',
 'Короткая история с вопросом. Меняй порядок упоминания входных величин; не копируй дерево формулы словами.',
 'Точная инструкция, выделяющая порядок действий и направление вычитания или деления. Без алгебраической записи.',
 'Правило простой игры: очки, движение, ресурсы, штрафы. Условие самодостаточно, без дополнительных правил.',
 'Учебный пример по мотивам старых книг о калькуляторах. Современный ясный русский язык, без лишних сведений.',
 'Краткое техническое задание. Иногда сначала укажи желаемый результат, затем опиши входы.',
]


def teacher_prefix(text):
    """Lex a whitelisted preorder stream; preserve every operator and operand."""
    try:return parse_prefix(text)
    except (ValueError,TypeError,AttributeError):pass
    if not isinstance(text,str):raise ValueError('Missing teacher prefix')
    compact=re.sub(r'\s+','',text)
    tokens=re.findall(r'R[0-3]|square|abs|neg|[+*/(),-]',compact)
    if ''.join(tokens)!=compact:raise ValueError('Unknown teacher expression symbol')
    depth=0
    for token in tokens:
        if token=='(':depth+=1
        elif token==')':
            depth-=1
            if depth<0:raise ValueError('Unbalanced teacher brackets')
    if depth:raise ValueError('Unbalanced teacher brackets')
    # In preorder, fixed operator arities uniquely determine the AST. Optional
    # grouping and separators cannot change it. Infix, postfix, extra operands,
    # missing arguments and unknown symbols fail the unchanged strict parser.
    return parse_prefix(' '.join(t for t in tokens if t not in ['(',')',',']))


def annotation(expr,roles,steps):
    """Check every teacher intermediate computation against the blinded parse."""
    if not isinstance(roles,dict)or set(roles)!=registers_used(expr):raise ValueError('Incorrect roles')
    if any(not isinstance(v,str)or not 1<=len(v.split())<=12 for v in roles.values()):raise ValueError('Role length')
    if not isinstance(steps,list)or len(steps)!=opcount(expr):raise ValueError('Step count')
    values={k:k for k in roles};out=[]
    for i,item in enumerate(steps):
        op=item['op'];args=item['args']
        if op not in ARITY or not isinstance(args,list)or len(args)!=ARITY[op]or any(a not in values for a in args):raise ValueError('Invalid step')
        value=[op,*(values[a]for a in args)];values['t'+str(i+1)]=value
        # Render the verified machine-readable teacher steps canonically. This
        # prevents a contradictory free-text rationale becoming a target.
        a=args[0];b=args[1]if len(args)==2 else''
        word={'+':f'Сложить {a} и {b}', '-':f'Из {a} вычесть {b}',
          '*':f'Умножить {a} на {b}', '/':f'Разделить {a} на {b}',
          'abs':f'Взять модуль {a}','neg':f'Сменить знак {a}','square':f'Возвести {a} в квадрат'}[op]
        out.append({'op':op,'args':args,'result':'t'+str(i+1),'explanation':word+'; результат t'+str(i+1)})
    if canonical(value)!=canonical(expr):raise ValueError('Steps do not compute parsed expression')
    return roles,out


def jobs():
    rng=random.Random(6116002);out=[]
    documents=[d for d in read(BUILD/'training/domain-documents.jsonl')if d['kind']in ['book_prose','historical_game']]
    if not documents:documents=read(BUILD/'training/domain-documents.jsonl')
    for partition,count in [('train',512),('validation',48)]:
        sources=[d for d in documents if ('validation'if int(hashlib.sha256(d['id'].encode()).hexdigest()[:8],16)%5==0 else'train')==partition]
        for i in range(count):
            level=1 if i%10==0 else 2 if i%2==0 else 3
            for attempt in range(1000):
                expr=distinct(rng.choice(shapes(level)),rng.sample(['R0','R1','R2','R3'],4))
                if stack_depth(expr)>4:continue
                # Avoid trivial repeated unary operations that erase the need
                # to learn the requested number of semantic decisions.
                if any(op+'('+op+'('in canonical(expr)for op in ['abs','neg']):continue
                if ARITY[expr[0]]==2:
                    alternate=[expr[0],expr[2],expr[1]]if expr[0]in ['-','/']else[rng.choice(['-','/']),*expr[1:]]
                else:
                    alternate=[rng.choice([o for o in ['abs','neg','square']if o!=expr[0]]),*expr[1:]]
                if canonical(expr)!=canonical(alternate):break
            family=f'{partition}-scenario-{i:04d}'
            source=sources[rng.randrange(len(sources))]
            for k,e in enumerate([expr,alternate]):out.append({'id':family+f'-{k}','language_family':family,'split':partition,
              'expression':e,'level':level,'style':i%len(STYLES),'source_id':source['id'],
              'source_hint':source['text'][:420]})
    return out


def status(phase,**extra):
    row={'phase':phase,**extra};write_json(ROOT/'teacher/status.json',row);print(json.dumps(row,ensure_ascii=False),flush=True)


def main():
    root=ROOT/'teacher';root.mkdir(exist_ok=True)
    if(root/'manifest.json').exists():print('Semantic teacher data already complete');return
    frozen=json.loads((ROOT/'audit-frozen.json').read_text());assert all(sha(ROOT/name)==v['sha256']for name,v in frozen['files'].items())
    started=time.monotonic();work=jobs();errors=[];generated=[]
    if(root/'jobs.json').exists():assert json.loads((root/'jobs.json').read_text())==work,'Cached generation jobs changed'
    write_json(root/'jobs.json',work)
    assert not {j['source_id']for j in work if j['split']=='train'}&{j['source_id']for j in work if j['split']=='validation'}
    snapshot=root/'source';snapshot.mkdir(exist_ok=True)
    if(root/'candidates.jsonl').exists()and not(root/'source-initial-generation').exists():
        __import__('shutil').copytree(snapshot,root/'source-initial-generation')
    for name in ['semantic_teacher.py','teacher_data.py','semantic_common.py','semantic_freeze.py']:
        __import__('shutil').copyfile(__import__('pathlib').Path(__file__).parent/name,snapshot/name)
    def generate(job):
        system=('Ты составляешь условия задач для маленькой русской модели МК-61. Верни только JSON-массив из шести разных строк. '
          'В каждой строке 10–55 слов: самостоятельное точное условие, без готового решения, формулы, HEX, числовых примеров. '
          'Оно должно точно задавать целевое дерево. Операторы +,-,*,/,abs,neg,square; abs — модуль, neg — смена знака, square — квадрат. '
          'Назови каждый нужный регистр R0,R1,R2,R3 и роль хранимой величины. Все входы только читаются, результат в X. '
          'Не добавляй константы, округления, сравнения и дополнительные действия. Различай порядок операндов и порядок действий. '
          'Деление не означает деление нацело. Подписанные величины разрешены. Если сюжет не подходит формуле, дай ясную инструкцию. '
          'Фрагмент книги или игры — только источник тематики: не копируй лишние операции из него. '
          'Шесть условий должны отличаться смысловым изложением, а не перестановкой одинаковых слов.')
        user=STYLES[job['style']]+'\nИсточник тематики: '+job['source_hint']+'\nЦель: '+expression_text(job['expression'])+'\nДерево: '+json.dumps(job['expression'])
        response=teacher_data.call(root,'generate',job['id'],[{'role':'system','content':system},{'role':'user','content':user}],tokens=2600,temperature=.65)
        out=[]
        for i,text in enumerate(response if isinstance(response,list)else[]):
            if not isinstance(text,str):continue
            text=re.sub(r'Р([0-3])',r'R\1',text).strip()
            if not 8<=len(text.split())<=65 or any(x in text for x in '<>=`')or not no_side_effects(text):continue
            if set(re.findall(r'R[0-9A-F]',text))!=registers_used(job['expression']):continue
            out.append({k:v for k,v in job.items()if k not in ['source_hint','id']}|{'id':job['id']+f':{i}','task':text,'pair_id':job['language_family']+f':{i}'})
        return out
    if(root/'candidates.jsonl').exists():
        generated=read(root/'candidates.jsonl');status('cached_generation_loaded',candidates=len(generated))
    else:
        with ThreadPoolExecutor(max_workers=8)as pool:
            futures={pool.submit(generate,j):j['id']for j in work}
            for n,f in enumerate(as_completed(futures),1):
                try:generated+=f.result()
                except Exception as e:errors.append({'stage':'generate','id':futures[f],'error':str(e)[:200]})
                if n%16==0 or n==len(work):status('generation',jobs=n,total=len(work),candidates=len(generated),errors=len(errors),seconds=time.monotonic()-started)
    generated.sort(key=lambda x:x['id']);save_jsonl(root/'candidates.jsonl',generated)
    rng=random.Random(6116003);rng.shuffle(generated);batches=[generated[i:i+6]for i in range(0,len(generated),6)]
    def verify(index,batch):
        opaque={hashlib.sha256(('semantic-blind:'+r['id']).encode()).hexdigest()[:18]:r for r in batch}
        system=('Самостоятельно восстанови алгоритм только по условию. Ответ только JSON-массив объектов '
          '{"id":"...","prefix":"...","roles":{"R0":"роль величины"},"steps":[{"op":"-","args":["R0","R1"]}]}. '
          'prefix — префиксная формула, без скобок: операция перед аргументами. Операции +,-,*,/ имеют два аргумента; abs,neg,square один. '
          'Листья R0,R1,R2,R3. roles содержит каждый использованный вход и короткое описание его роли. '
          'steps — вычисления снизу вверх; результат первого шага называется t1, второго t2 и т.д.; '
          'args содержит исходные регистры или результаты ПРЕДЫДУЩИХ шагов. Последний шаг обязан вычислять весь ответ. '
          'Пример формата шагов для суммы разности и числа: [{"op":"-","args":["R0","R1"]},{"op":"+","args":["t1","R2"]}]. '
          'При неоднозначности, лишних действиях, неполных ролях или требовании писать в исходную память верни prefix=null. '
          'Не угадывай формулу по соседним условиям. Каждая строка независима.')
        identity=f'{index:04d}-'+hashlib.sha256(json.dumps(batch,ensure_ascii=False).encode()).hexdigest()[:16]
        result=teacher_data.call(root,'blind-roles-steps',identity,[{'role':'system','content':system},
          {'role':'user','content':json.dumps([{'id':key,'text':r['task']}for key,r in opaque.items()],ensure_ascii=False)}],tokens=3600,temperature=0)
        parsed={x.get('id'):x for x in result if isinstance(x,dict)}if isinstance(result,list)else{}
        good=[];bad=[]
        for key,row in opaque.items():
            try:
                value=parsed[key];expr=teacher_prefix(value['prefix'])
                if canonical(expr)!=canonical(row['expression']):raise ValueError('Blinded expression mismatch')
                roles,steps=annotation(expr,value['roles'],value['steps'])
                good.append({**row,'roles':roles,'steps':steps,'source':'semantic_teacher_new',
                  'teacher_raw':f'blind-roles-steps/{identity}.json','semantic_check':'independent_call_same_teacher_exact_AST_mod_commutativity'})
            except (ValueError,TypeError,KeyError,AttributeError)as e:bad.append({'id':row['id'],'reason':str(e),'blinded':parsed.get(key)})
        return good,bad
    good=[];bad=[]
    with ThreadPoolExecutor(max_workers=8)as pool:
        futures={pool.submit(verify,i,b):i for i,b in enumerate(batches)}
        for n,f in enumerate(as_completed(futures),1):
            try:
                g,b=f.result();good+=g;bad+=b
            except Exception as e:errors.append({'stage':'verify','batch':futures[f],'error':str(e)[:200]})
            if n%16==0 or n==len(batches):status('blind_verification',batches=n,total=len(batches),accepted=len(good),rejected=len(bad),errors=len(errors),seconds=time.monotonic()-started)
    save_jsonl(root/'verified-before-emulator.jsonl',sorted(good,key=lambda r:r['id']));save_jsonl(root/'rejected.jsonl',bad)
    # The reference checker is deliberately sequential: the emulator core has
    # global state. No model/teacher ever receives the new audit conditions.
    forbidden={wording_key(t['task'])for t in read(ROOT/'audit.jsonl')}
    for name in ['development1','development2','development3','fresh1','fresh2','fresh3']:
        forbidden.update(wording_key(t['task'])for t in read(BUILD/'codec-qat-v1'/(name+'.jsonl')))
    byword=collections.defaultdict(list)
    for row in good:byword[wording_key(row['task'])].append(row)
    em=Emulator(build(root/'libreference.so'));partitions=collections.defaultdict(list);drops=collections.Counter()
    for key,group in sorted(byword.items()):
        if key in forbidden:drops['exact_observed_or_audit_overlap']+=len(group);continue
        if len({r['split']for r in group})>1:drops['cross_split_wording']+=len(group);continue
        row=sorted(group,key=lambda x:x['id'])[0]
        try:task=make_task(row['task'],row['expression'],random.Random(int(hashlib.sha256(row['id'].encode()).hexdigest()[:12],16)),row['id'],split=row['split'],emulator=em)
        except ValueError:drops['invalid_real_core_reference']+=1;continue
        partitions[row['split']].append({**row,**task})
    for partition,rows in partitions.items():save_jsonl(root/(partition+'.jsonl'),rows)
    if len(partitions['train'])<3000:raise ValueError('Fewer than 3000 verified train conditions: '+str(len(partitions['train'])))
    manifest={'teacher':teacher_data.MODEL,'endpoint':teacher_data.URL,'jobs':len(work),'candidates':len(generated),
      'partitions':{k:len(v)for k,v in partitions.items()},'drops':dict(drops),'errors':errors,'seconds':time.monotonic()-started,
      'families_partitioned_before_generation':True,'source_documents_ground_topics_only':True,
      'checker_sees_target_expression':False,'checker_and_generator_same_model':True,
      'short_step_text_rendered_from_verified_teacher_steps':True,'new_audit_conditions_sent_to_teacher':False,
      'teacher_prefix_formats':'whitelisted flat, compact or grouped preorder; unchanged operator/operand stream and strict arity parse',
      'generation_jobs_without_cached_valid_response':[j['id']for j in work if not(root/'teacher-raw/generate'/(j['id']+'.json')).exists()],
      'real_mk61_reference_execution_cases_each':9,'files':{p.name:sha(p)for p in [root/'train.jsonl',root/'validation.jsonl']}}
    write_json(root/'manifest.json',manifest);status('complete',**manifest)


if __name__=='__main__':main()
