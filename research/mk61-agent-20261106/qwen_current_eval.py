"""Read-only Qwen baseline on the exact BJ tasks, with an HTTP JSON adapter.

The model receives a task-independent codec/ISA manual, not test solutions.
The gold-checker arm is privileged diagnostic feedback, never a deployable agent.
"""
import concurrent.futures
import copy
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request

from bj_common import ROOT as SOURCE, read, rows, write, sha
from bj_runtime import Session as OrdinarySession
from bh_spec import install
import bj_eval
import ay_eval as core
from ay_codec import UNARY_NAMES, BINARY_NAMES, to_program
from ha_protocol import parse_bytes
from full_isa_vm import FullVM
from ar_spec import equivalent, verify
from au_teacher import REFERENCE

ROOT = SOURCE.parent / 'qwen-current-comparison-v1'
MODEL = 'Qwen/Qwen3.8-Flash-Next-FP8'
URL = 'http://127.0.0.1:18086/v1/chat/completions'


def manual():
    return (
        'Ты работаешь с инструментами МК-61. Отвечай одним JSON action/body. '
        'DONE утверждает правильность решения исходного русского условия; stopped означает только останов. '
        'Гипотеза SPEC может быть неверна. WRITE заменяет код и запускает текущий публичный случай. '
        'RUN: ровно один HEX-байт номера случая. TRACE,DONE,UNSURE: пустой body. '
        'DIAG:5 HEX-байтов. DIAG 04 FF FF 00 00 означает ошибку гипотезы и вызывает новый разбор условия без изменения кода. '
        'WRITE возвращает НЕ машинные команды, а следующую компактную SPEC. '
        'Все байты разделяй пробелами. Первый байт FF=сохранять память;00..0E=записать результат также в R0..RE. '
        'Далее ровно одно префиксное дерево выражения. Лист00..0E=исходный регистр R0..RE; '
        '10 kk=константа по индексу kk из таблицы;11=pi. '
        'Унарные байты: ' + ','.join(f'{0x20+i:02X}={op}' for i,op in enumerate(UNARY_NAMES)) + '. '
        'Бинарные байты: ' + ','.join(f'{0x40+i:02X}={op}' for i,op in enumerate(BINARY_NAMES)) + '. '
        'После унарного байта один аргумент; после бинарного — левый и правый аргументы. '
        'Не дополняй SPEC лишними байтами, STOP или нулями. Максимум31узел. '
        'Пример формата: квадрат R7 с сохранением памяти: FF '+f'{0x20+UNARY_NAMES.index("square"):02X}'+' 07. '
        'Пример R7 минус R8 с сохранением памяти: FF 41 07 08. '
        'Текущий код в пользовательском состоянии, напротив, показан в HEX машинных команд; его таблица ниже. '
        'После отклонённого DONE исправляй код либо ошибочную гипотезу; повтор того же DONE не исправляет результат. '
        'Завершающий символ < в тексте состояния — маркер старого протокола; верни JSON, а не его продолжение.\n'
        + REFERENCE.split('WRITE —')[0])


class Actor:
    def __init__(self):
        self.pool = concurrent.futures.ThreadPoolExecutor(8)
        self.locks = {}; self.guard = threading.Lock(); self.system = manual()
        self.calls = 0

    def one(self, prompt, forced):
        actions = [forced] if forced else ['write','run','trace','done','unsure','diag']
        schema = {'type':'object','properties':{'action':{'type':'string','enum':actions},'body':{'type':'string'}},
                  'required':['action','body'],'additionalProperties':False}
        payload = {'model':MODEL,'messages':[{'role':'system','content':self.system},{'role':'user','content':prompt}],
            'temperature':0,'seed':26110873,'max_tokens':1024,
            'chat_template_kwargs':{'enable_thinking':False,'thinking':False},
            'response_format':{'type':'json_schema','json_schema':{'name':'mk61_action','strict':True,'schema':schema}}}
        data = json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()
        path = ROOT/'cache'/(hashlib.sha256(data).hexdigest()+'.json'); path.parent.mkdir(exist_ok=True)
        with self.guard:
            lock = self.locks.setdefault(str(path),threading.Lock())
        with lock:
            if path.exists():
                cached = read(path)
            else:
                started = time.monotonic()
                for attempt in range(3):
                    try:
                        request = urllib.request.Request(URL,data,{'Content-Type':'application/json'})
                        with urllib.request.urlopen(request,timeout=180) as stream:
                            response = json.load(stream)
                        break
                    except Exception:
                        if attempt == 2: raise
                        time.sleep(2)
                cached = {'request':payload,'response':response,'seconds':time.monotonic()-started}; write(path,cached)
        response = cached['response']; message = response['choices'][0]['message']; content = message.get('content') or ''
        try:
            value = json.loads(content); action = value['action']; body = parse_bytes(value['body'],empty=True)
            if action not in actions: raise ValueError('ACTION')
            if action in ['done','trace','unsure'] and body: raise ValueError('UNEXPECTED_BODY')
            if action == 'run' and len(body)!=1: raise ValueError('RUN_LENGTH')
            if action == 'diag' and len(body)!=5: raise ValueError('DIAG_LENGTH')
            error = None
        except (ValueError,KeyError,TypeError) as failure:
            action = None; body = []; error = str(failure)
        usage = response.get('usage') or {}
        with self.guard:
            self.calls += 1
            if self.calls % 16 == 0:
                write(ROOT/'request-status.json',{'calls':self.calls,'unix':time.time()})
        return {'action':action,'body':body,'codec_error':error,'raw':content,'usage':usage,
                'generated_token_ids':[], 'token_ids_unavailable_over_HTTP':True,
                'input_tokens':usage.get('prompt_tokens',0),'completion_tokens':usage.get('completion_tokens',0),
                'finish_reason':response['choices'][0].get('finish_reason'),'seconds':cached['seconds']}

    def generate(self, model, tokenizer, prompts, forced_action=None):
        return list(self.pool.map(lambda p:self.one(p,forced_action),prompts))


class GoldCheckerSession(OrdinarySession):
    def __init__(self, goal, *args, **kwargs):
        self.oracle_spec = copy.deepcopy(goal['spec'])
        super().__init__(goal,*args,**kwargs)

    def apply_action(self, action, body):
        if action != 'done': return super().apply_action(action,body)
        visible = self.declared_spec
        try:
            self.declared_spec = self.oracle_spec
            result = super().apply_action(action,body)
        finally:
            self.declared_spec = visible
        if result == 'done_rejected' and self.gate_checks[-1].get('reason')=='COUNTEREXAMPLE':
            c = self.gate_checks[-1]
            # Privileged expected numerical feedback, but no gold formula in the prompt.
            self.observation = 'DONE_REJECTED. Контрольный пример: '+json.dumps(c.get('inputs',{}),ensure_ascii=False,separators=(',',':'))
            self.observation += '; '+c['name']+'='+str(c['actual'])+', ожидается '+format(c['expected'],'.8g')+'.'
            self.history[-1]['observation'] = self.observation
        return result


def main():
    install(); ROOT.mkdir(exist_ok=True)
    dataset = SOURCE/'closed-clean.jsonl'; policy = read(ROOT/'policy.json')
    assert sha(dataset)==policy['dataset_sha256']
    assert sha(__file__)==policy['driver_sha256']
    actor = Actor(); core.generate = actor.generate; bj_eval.generate = actor.generate
    goals = rows(dataset); vm = FullVM(); started = time.monotonic()
    deadline = time.monotonic()+1800
    while True:
        try:
            with urllib.request.urlopen(URL.replace('/chat/completions','/models'),timeout=5) as stream:
                available=json.load(stream)
            assert any(m['id']==MODEL for m in available['data'])
            break
        except Exception:
            if time.monotonic()>deadline:raise RuntimeError('Qwen startup deadline exceeded')
            write(ROOT/'status.json',{'phase':'waiting_for_Qwen','unix':time.time()});time.sleep(10)
    if not(ROOT/'preflight.json').exists():
        from bj_runtime import goal_state, render
        from az_teacher import pool_for
        probes=[]
        for name,text,expr in [('square_R7','Вычисли квадрат R7.',['square','R7']),
                               ('subtract','Вычти R8 из R7.',['-','R7','R8'])]:
            spec={'X':expr,'writes':{},'angle':'DEG'};pool=pool_for(text)
            goal={'id':'protocol:'+name,'task':text,'spec':spec,'pool':pool,'public_inputs':[{'R7':'2.25','R8':'-1.5'},{'R7':'-3.25','R8':'0.875'}]}
            p=render(goal_state(goal),'spec');v=actor.one(p,'write');program=[]
            if not v['codec_error']:
                program,_=to_program(v['body'],pool,'DEG','spec')
            check=verify(vm,program,pool,spec,goal['public_inputs'])
            probes.append({'id':name,'generation':v,'ROM_check':check})
        write(ROOT/'preflight.json',probes)
    assert all(x['ROM_check']['status']=='TESTED'for x in read(ROOT/'preflight.json')),'Protocol preflight failed; do not launch the full exam'
    if not (ROOT/'primary.json').exists():
        values = []
        for at in range(0,len(goals),24):
            values += core.primary(None,None,goals[at:at+24],'spec',vm)
            write(ROOT/'status.json',{'phase':'primary','completed':len(values),'total':len(goals),'unix':time.time()})
        summary = core.primary_metrics(values)
        summary['mean_generated_tokens'] = sum(x['generation']['completion_tokens'] for x in values)/len(values)
        write(ROOT/'primary.json',{'summary':summary,'records':values})
    primary = read(ROOT/'primary.json'); plans = {r['id']:r for r in primary['records']}
    cohort = core.choose_runtime(goals,256,261111117)
    for mode, session in [('own_spec',OrdinarySession),('gold_checker',GoldCheckerSession)]:
        if (ROOT/(mode+'.json')).exists(): continue
        bj_eval.Session = session; records = []
        # Use the original full-cohort ordering: mutation-kind cycles must not reset.
        # Only the HTTP dispatch is parallel; actual emulator operations stay serial.
        write(ROOT/'status.json',{'phase':mode,'completed':0,'total':512,'unix':time.time()})
        records = bj_eval.episodes(None,None,cohort,plans,vm,'self')
        write(ROOT/(mode+'.json'),{'summary':bj_eval.metrics(records),'records':records})
    own = read(ROOT/'own_spec.json'); gold = read(ROOT/'gold_checker.json')
    assert all(a['id']==b['id'] and a['history'][0].get('prompt')==b['history'][0].get('prompt')
               for a,b in zip(own['records'],gold['records']))
    result = {'model':MODEL,'optimizer_updates':0,'dataset_sha256':sha(dataset),'primary':primary['summary'],
              'own_spec':own['summary'],'gold_checker':gold['summary'],
              'gold_formula_not_shown_to_actor':True,'gold_numerical_feedback_is_privileged':True,
              'initial_prompts_identical_between_checker_arms':True,'seconds':time.monotonic()-started,
              'reference_assisted_protocol':True,'thinking':False,'service_context':8192,'action_budget':12}
    write(ROOT/'results.json',result); write(ROOT/'complete.json',{'complete':True,'optimizer_updates':0,'unix':time.time()})
    write(ROOT/'status.json',{'phase':'complete','unix':time.time()}); print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
