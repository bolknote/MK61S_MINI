"""Pilot fixed before model responses; independent arithmetic and ROM validation."""
import copy
import random
import time
from ar_common import ROOT, HERE, MODEL, write, sha
from ar_spec import verify, infer, equivalent
from full_isa_math import compile_expr
from full_isa_protocol import REGISTERS
from full_isa_vm import FullVM
from ha_protocol import constants, encode, assemble


def definitions():
    c = lambda x: {'constant': str(x)}
    return [
        ('unary', 'Вычисли синус числа из R0, результат оставь в X.', ['sin','R0'], 'DEG', None, 'angle'),
        ('unary', 'Найди косинус R0 и возведи полученный результат в квадрат.', ['square',['cos','R0']], 'RAD', None, 'signed'),
        ('unary', 'Возьми квадрат числа из R0, затем ещё раз возведи результат в квадрат.', ['square',['square','R0']], 'RAD', None, 'signed'),
        ('unary', 'Вычисли квадратный корень из модуля R0.', ['sqrt',['abs','R0']], 'RAD', None, 'signed'),
        ('unary', 'Возьми натуральный логарифм R0 и поменяй знак результата.', ['neg',['ln','R0']], 'RAD', None, 'positive'),
        ('unary', 'Отсеки дробную часть R0 к нулю и возведи оставшуюся целую часть в квадрат.', ['square',['int','R0']], 'RAD', None, 'signed'),
        ('unary', 'Найди модуль дробной части числа из R0.', ['abs',['frac','R0']], 'RAD', None, 'signed'),
        ('unary', 'Вычисли арксинус R0, ответ в градах.', ['asin','R0'], 'GRAD', None, 'unit'),
        ('binary', 'Вычти R1 из R0.', ['-','R0','R1'], 'RAD', None, 'signed'),
        ('binary', 'Раздели R0 на R1.', ['/','R0','R1'], 'RAD', None, 'signed'),
        ('binary', 'Сложи R0 и число 2.5.', ['+','R0',c(2.5)], 'RAD', None, 'signed'),
        ('binary', 'Умножь R1 на R0.', ['*','R1','R0'], 'RAD', None, 'signed'),
        ('binary', 'Вычти R0 из числа 3.', ['-',c(3),'R0'], 'RAD', None, 'signed'),
        ('binary', 'Раздели число 1 на сумму R0 и числа 4.', ['/',c(1),['+','R0',c(4)]], 'RAD', None, 'signed'),
        ('binary', 'Сложи квадрат R0 и квадрат R1.', ['+',['square','R0'],['square','R1']], 'RAD', None, 'signed'),
        ('binary', 'Вычисли R0 в степени R1.', ['pow','R0','R1'], 'RAD', None, 'positive'),
        ('mixed', 'Сложи синус R0 в градусах с квадратом R1.', ['+',['sin','R0'],['square','R1']], 'DEG', None, 'angle'),
        ('mixed', 'Вычисли квадрат разности R0 и R1, затем прибавь R2.', ['+',['square',['-','R0','R1']],'R2'], 'RAD', None, 'signed'),
        ('mixed', 'Умножь сумму R0 и R1 на R2.', ['*',['+','R0','R1'],'R2'], 'RAD', None, 'signed'),
        ('mixed', 'Из произведения R0 и R1 вычти квадрат R2.', ['-',['*','R0','R1'],['square','R2']], 'RAD', None, 'signed'),
        ('mixed', 'Раздели модуль разности R0 и R1 на R2.', ['/', ['abs',['-','R0','R1']], 'R2'], 'RAD', None, 'signed'),
        ('mixed', 'Прибавь 1 к квадратному корню из суммы квадрата R0 и числа 2.', ['+',['sqrt',['+',['square','R0'],c(2)]],c(1)], 'RAD', None, 'signed'),
        ('mixed', 'Вычисли косинус суммы R0 и R1 в радианах.', ['cos',['+','R0','R1']], 'RAD', None, 'signed'),
        ('mixed', 'Вычти квадрат суммы R0 и R1 из квадрата их разности.', ['-',['square',['-','R0','R1']],['square',['+','R0','R1']]], 'RAD', None, 'signed'),
        ('memory', 'Возведи R0 в квадрат. Результат сохрани в R3 и оставь в X.', ['square','R0'], 'RAD', 'R3', 'signed'),
        ('memory', 'Вычисли синус R0 в градусах, сохрани его в R4 и оставь в X.', ['sin','R0'], 'DEG', 'R4', 'angle'),
        ('memory', 'Сложи R0 и R1. Сумму запиши в R0 и оставь в X.', ['+','R0','R1'], 'RAD', 'R0', 'signed'),
        ('memory', 'Вычти R1 из R0. Разность запиши в R1 и оставь в X.', ['-','R0','R1'], 'RAD', 'R1', 'signed'),
        ('memory', 'Умножь квадрат R0 на R1. Запиши результат в R5 и оставь в X.', ['*',['square','R0'],'R1'], 'RAD', 'R5', 'signed'),
        ('memory', 'Найди квадратный корень из суммы квадратов R0 и R1. Запиши его в R2 и оставь в X.', ['sqrt',['+',['square','R0'],['square','R1']]], 'RAD', 'R2', 'signed'),
        ('memory', 'Из модуля R0 вычти R2. Запиши результат в RE и оставь в X.', ['-',['abs','R0'],'R2'], 'RAD', 'RE', 'signed'),
        ('memory', 'Вычисли дробную часть R0, умноженную на R1. Результат запиши в R6 и оставь в X.', ['*',['frac','R0'],'R1'], 'RAD', 'R6', 'signed'),
    ]


def bank(profile, seed, count):
    rng = random.Random(seed)
    ranges = {'signed':(-2.75,3.5), 'positive':(.25,3.5), 'unit':(-.8,.8), 'angle':(-70,70)}
    lo, hi = ranges[profile]
    result = []
    for i in range(count):
        values = {r: str(round(rng.uniform(-8,8),4)) for r in REGISTERS}
        values.update(X='0.37',Y='-0.82',Z='1.23',T='-2.41')
        # Fixed valid boundaries and random interior, with nonzero denominators.
        x = [lo, hi, (lo+hi)/2, .625][i] if i < 4 else rng.uniform(lo,hi)
        values.update(R0=str(round(x,4)), R1=str(round(rng.uniform(.25,3.5),4)),
                      R2=str(round(rng.uniform(.4,3.5),4)))
        result.append(values)
    return result


def mutation(body, pool, spec, cases, vm, index):
    code = assemble(body,pool,'asm')
    candidates=[]
    # Distinct instruction errors, not arbitrary numbers or malformed macros.
    for at, op in enumerate(code):
        changes = {0x22:0x21,0x1C:0x1D,0x1D:0x1C,0x10:0x11,0x11:0x10,
                   0x12:0x13,0x13:0x12,0x31:0x0B,0x35:0x34}
        if op in changes:candidates.append(('operation',code[:at]+[changes[op]]+code[at+1:]))
        if 0x60<=op<=0x6E:candidates.append(('argument',code[:at]+[0x60+(op-0x60+1)%3]+code[at+1:]))
    for at in range(len(code)-1):
        if 0x60<=code[at]<=0x6E and 0x60<=code[at+1]<=0x6E:
            candidates.append(('order',code[:at]+[code[at+1],code[at]]+code[at+2:]))
    preferred=['operation','argument','order'][index%3]
    candidates.sort(key=lambda x:x[0]!=preferred)
    for kind, raw in candidates:
        candidate=encode(raw,pool,'asm')
        result=verify(vm,candidate,pool,spec,cases)
        if result['status']=='FAIL':return kind,candidate,result
    raise AssertionError('No nontrivial mutation')


def main():
    assert not (ROOT/'frozen.json').exists(), 'Pilot is immutable after freeze'
    vm=FullVM();goals=[];checks=0
    for i,(family,text,expr,angle,store,profile) in enumerate(definitions()):
        text += ' Остальные регистры памяти сохрани; после вычисления остановись.'
        spec={'X':expr,'writes':{store:expr}if store else{},'angle':angle}
        pool=constants(text)
        raw=compile_expr(expr)+([0x40+int(store[1:],16)]if store else[])+[0x50]
        body=encode(raw,pool,'asm')
        public=bank(profile,230001+i,2)
        checker=bank(profile,240001+i,24)
        audit=bank(profile,250001+i,32)
        for cases in [public,checker,audit]:
            result=verify(vm,body,pool,spec,cases)
            assert result['status']=='TESTED',(i,result)
            checks+=result['cases']
        inferred=infer(body,pool,angle)
        assert equivalent(inferred,spec,audit)['tested_equal'],i
        fault,wrong,witness=mutation(body,pool,spec,checker+audit,vm,i)
        goals.append({'id':f'ar-{i:02d}','family':family,'task':text,'angle':angle,'pool':pool,
                      'spec':spec,'reference_body':body,'wrong_body':wrong,'fault':fault,
                      'fault_witness':witness,'public_inputs':public,'checker_inputs':checker,
                      'audit_inputs':audit,'domain_profile':profile})
    write(ROOT/'goals.json',goals)
    policy={'goals':32,'initial_programs':['correct','wrong'],'input_modes':['natural','formal'],
            'gate_modes':['raw','mechanical'],'models':['small-q4-aq-full-step2500','Qwen3.8-Flash-Next-FP8'],
            'max_turns':12,'small_body_max_tokens':511,'small_context':1024,
            'teacher_max_output_tokens':512,'teacher_temperature':0,'teacher_thinking':False,
            'checker_cases':24,'audit_cases':32,'tolerance':2e-6,'scope':'one-shot straight-line arithmetic and stores',
            'natural_spec':'goal-only forced WRITE decoded before seeing candidate; no gold substitution',
            'formal_spec':'verified gold supplied as task definition',
            'test_status':'TESTED; finite numerical tests, not proof',
            'training_updates':0,'selection':'fixed AQ full step2500; no selection on pilot',
            'final_test_policy':'This diagnostic set is opened only after frozen source/model policy. Future training must use new final tests.'}
    write(ROOT/'policy.json',policy)
    sources={p.name:sha(p)for p in HERE.glob('*.py')if p.name.startswith('ar_')}
    # Protect all transitively used legacy research files as well, without editing them.
    sources.update({p.name:sha(p)for p in HERE.glob('*.py')if not p.name.startswith('ar_')})
    write(ROOT/'frozen.json',{'unix':time.time(),'sources':sources,'goals_sha256':sha(ROOT/'goals.json'),
                             'policy_sha256':sha(ROOT/'policy.json'),'reference_ROM_cases':checks,
                             'small_packet_sha256':sha(MODEL/'model.mkqb'),
                             'small_master_sha256':sha(MODEL/'hf/model.safetensors'),
                             'ROM_library_sha256':sha(__import__('full_isa_vm').ROOT/'libfullisa.so'),
                             'symbolic_reference_matches':32,'model_outputs_seen':False})
    print({'frozen_goals':len(goals),'reference_ROM_cases':checks,'training_updates':0})


if __name__=='__main__':main()
