#!/usr/bin/env python3
"""Whole-five-chip CONDITIONAL first stack-lift export on the exact ring.

Baseline reproduces every recorded native macro boundary. Counterfactual:
the detached symbolic primary state has R41=F and arbitrary raw6; no such
state is injected into the reference calculator. This is NOT native success.
The enabled-lift continuation uses the same fixed key release as the native
pressSequence, not a controller-dependent or feedback-driven key schedule.
"""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys

from z3 import BitVec, is_bv_value, simplify, sat
from z3.z3util import get_vars

root=Path(__file__).resolve().parent
w=runpy.run_path(str(root/'cache46-writer-contracts.py'))
q=w['q']
native=json.loads(subprocess.check_output(
    ['node',str(root/'cache-stack-lift-native.cjs'),'--proof-input'],text=True))
rom_hash=hashlib.sha256(q['ROM_PATH'].read_bytes()).hexdigest()
assert rom_hash=='6c3f85b3e942cdd4d4191e46e98a50829eb850011b8b7a3cc01b12e5e2a31a33'
models={'ik1302':q}
for chip,rom_name in (('ik1303','ИК1303'),('ik1306','ИК1306')):
    model=runpy.run_path(str(root/'ik1302_symbolic.py'))
    rom=json.loads(subprocess.check_output(
        ['node','-e','console.log(JSON.stringify(require(process.argv[1])[process.argv[2]]))',
         str(q['ROM_PATH']),rom_name],text=True))
    model['execute_command'].__globals__.update(
        COMMANDS=rom['команды'],SYNCS=rom['синхропрограммы'],MICROS=rom['микрокоманды'])
    models[chip]=model
names=('ir2a','ir2b','ik1302','ik1303','ik1306')
locations=((0,41),(0,83),(0,125),(0,167),(0,209),(0,251),
           (1,41),(1,83),(1,125),(1,167),(1,209),(1,251),
           (2,41),(3,41),(4,41))
slots=('marker','control','P7','P8','P9','P10','W','Q','Z','T','U','V','Y','X','X1')
raw=(0,3,9,12,18,21)
program=(14,17,20,23,26,29)


def move_tags(tags,j):
    for k in range(42):
        index=j+k
        old=[tags[name][index if name.startswith('ir') else k] for name in names]
        for name,value in zip(names,(old[4],old[0],old[1],old[2],old[3])):
            tags[name][index if name.startswith('ir') else k]=value


def make(entry):
    state={}
    for chip,model in models.items():
        a=model['State']('whole_ring_'+chip)
        for field in ('r','m','st'):
            setattr(a,field,[q['N4'](v) for v in entry['state'][chip][field]])
        for field in ('s','s1'):
            setattr(a,field,q['N4'](entry['state'][chip][field]))
        for field in ('l','t','carry'):
            setattr(a,field,q['N1'](entry['state'][chip][field]))
        state[chip]=a
    for name in names[:2]:state[name]=[q['N4'](v) for v in entry['state'][name]['m']]
    state['_wire']={name:{field:q['N4'](entry['state'][name][field])
                          for field in ('input','output')} for name in names}
    j=entry['state']['ir2a']['tick']
    assert j==entry['state']['ir2b']['tick']
    assert j==(84+42*entry['command'])%252
    assert all(entry['state'][name]['tick']==0 for name in models)
    tags={name:[None]*(252 if name.startswith('ir') else 42) for name in names}
    for slot,(index,end) in zip(slots,locations):
        for k in range(42):tags[names[index]][end-41+k]=(slot,k)
    for command in range(entry['command']):move_tags(tags,(84+42*command)%252)
    return state,tags,j


def boundary_ip(a,p=None):
    value=simplify(w['ip'](a))
    if is_bv_value(value):return value.as_long()
    assert p is not None,('symbolic controller requires a new case split',value)
    assert p.check()==sat
    chosen=p.model().eval(value,model_completion=True).as_long()
    w['prove'](p,value==chosen,'resolved whole-ring controller address',False)
    return chosen


def step(state,tags,j,pins,p=None):
    old_ir_a=state['ir2a'][j:j+42]
    incoming=state['ir2b'][j:j+42]
    emitted={}
    for chip,source in (('ik1302',incoming),('ik1303',None),('ik1306',None)):
        if source is None:source=emitted['ik1302' if chip=='ik1303' else 'ik1303']
        output=[]
        state[chip]=models[chip]['execute_command'](
            state[chip],boundary_ip(state[chip],p),*pins[chip],
            serial_inputs=source,emitted_outputs=output)
        emitted[chip]=output
    state['ir2a'][j:j+42]=emitted['ik1306']
    state['ir2b'][j:j+42]=old_ir_a
    # Match the real tick order, including primary.input being the PREVIOUS
    # IR2b output before closeRing replaces the last numeric memory cell.
    state['_wire']={
        'ik1302':{'input':incoming[-2],'output':emitted['ik1302'][-1]},
        'ik1303':{'input':emitted['ik1302'][-1],'output':emitted['ik1303'][-1]},
        'ik1306':{'input':emitted['ik1303'][-1],'output':emitted['ik1306'][-1]},
        'ir2a':{'input':emitted['ik1306'][-1],'output':old_ir_a[-1]},
        'ir2b':{'input':old_ir_a[-1],'output':incoming[-1]},
    }
    move_tags(tags,j)
    return (j+42)%252,emitted


def ring(state,tags):
    result={slot:[None]*42 for slot in slots}
    for name in names:
        memory=state[name] if name.startswith('ir') else state[name].m
        for tag,value in zip(tags[name],memory):
            slot,k=tag;assert result[slot][k] is None
            result[slot][k]=value
    assert all(v is not None for values in result.values() for v in values)
    return result


def validate_baseline():
    entries=native['completePrefix'];state,tags,j=make(entries[0])
    for entry,following in zip(entries,entries[1:]):
        assert boundary_ip(state['ik1302'])==entry['ip']
        pins={name:(entry['state'][name]['keyX'],entry['state'][name]['keyY'])
              for name in models}
        j,_=step(state,tags,j,pins)
        for name in names:
            target=following['state'][name]
            for field in ('input','output'):
                assert simplify(state['_wire'][name][field]).as_long()==target[field],(name,field)
            if name.startswith('ir'):
                assert [simplify(v).as_long() for v in state[name]]==target['m'],name
                assert j==target['tick']
                continue
            for field in ('r','m','st'):
                assert [simplify(v).as_long() for v in getattr(state[name],field)]==target[field],(name,field)
            for field in ('s','s1','l','t','carry'):
                assert simplify(getattr(state[name],field)).as_long()==target[field],(name,field)
    print('PASS: whole-ring symbolic engine reproduces ALL5 chips at',len(entries)-1,
          'consecutive native macro boundaries, including first E7.',flush=True)


def conditional_start(payload=None):
    entry=native['completePrefix'][0];state,tags,j=make(entry)
    if payload is None:payload=[BitVec('whole_ring_cache_%d'%k,4) for k in range(6)]
    for pos,value in zip(raw,payload):state['ik1302'].r[pos]=value
    # Conditional analysis only: this flag was 0 in the physical/native inlet.
    state['ik1302'].r[41]=q['N4'](15)
    original_payload=[entry['state']['ik1302']['r'][pos] for pos in raw]
    for name in names:
        memory=state[name] if name.startswith('ir') else state[name].m
        for k,(slot,nibble) in enumerate(tags[name]):
            if slot=='Y' and nibble in program:
                index=program.index(nibble)
                assert simplify(memory[k]).as_long()==original_payload[index]
                memory[k]=payload[index]
    initial_ring=ring(state,tags)
    p=q['base_solver'](state['ik1302'],0x8D);assert p.check()==sat
    pins={name:(entry['state'][name]['keyX'],entry['state'][name]['keyY']) for name in models}
    return entry,state,tags,j,payload,initial_ring,p,pins


def conditional_first_export():
    entry,state,tags,j,payload,initial_ring,p,pins=conditional_start()
    sequence=[];destination=None
    for count in range(100):
        code=boundary_ip(state['ik1302']);sequence.append(code)
        assert code not in (0xEE,0xE4,0xC9)
        before_ring=ring(state,tags)
        writer_slot=tags['ik1302'][1][0]
        before=state['ik1302'];j,emitted=step(state,tags,j,pins)
        if code==0xE7:
            destination=writer_slot
            w['prove'](p,w['eq'](emitted['ik1302'][1:36:3],w['A'](before)),
                       'conditional whole-ring first E7 stores exact A12')
            stored=ring(state,tags)[destination]
            w['prove'](p,w['eq']([stored[pos+1] for pos in raw],payload),
                       f'conditional raw6 really reached PHYSICAL {destination}, not only outgoing wire')
            final_ring=ring(state,tags)
            w['prove'](p,w['eq']([v for slot in slots for k,v in enumerate(final_ring[slot]) if k%3==2],
                               [v for slot in slots for k,v in enumerate(initial_ring[slot]) if k%3==2]),
                       'all15 complete program-lane pages remain unchanged through first export')
            break
        w['prove'](p,w['eq']([v for slot in slots for v in ring(state,tags)[slot]],
                           [v for slot in slots for v in before_ring[slot]]),
                   f'conditional whole-ring{code:02X} no ring changes',False)
    assert destination is not None
    # A held physical digit key is a fixed input schedule here, not feedback.
    assert entry['command']+len(sequence)<5*560
    print('CONDITIONAL route:',' '.join(f'{v:02X}' for v in sequence),flush=True)
    print('CONDITIONAL physical destination:',destination,'; all256^3 payloads;',
          'noEE/E4; native entryR41 was0, hypothetical flagF only.',flush=True)
    print('LIMIT: not a keyboard recipe, no proof of later survival or EE readback, '
          'not Ms exchange, not native partial K2.',flush=True)


def conditional_later_export(marker_payload=False):
    entry,state,tags,j,payload,initial_ring,p,pins=conditional_start()
    # The secondary chip's controller reacts differently to this marker.
    # Together the two exact cases cover all raw6, without choosing a path
    # from a model and pretending it applies to unconstrained payloads.
    p.add(payload[5]==15 if marker_payload else payload[5]!=15)
    writes=[];sequence=[]
    # Each press is one 560-macro held frame plus one 560-macro released
    # frame. The inlet is during the third key ('1') of F/Cx/1. Keep that
    # physical key through its original frame, then release at a fixed time.
    release_at=5*560
    assert 4*560 <= entry['command'] < release_at
    for count in range(1200):
        released=entry['command']+count>=release_at
        if released:pins['ik1302']=(0,0)
        code=boundary_ip(state['ik1302'],p);sequence.append(code)
        if code==0x35 and released:break
        assert code not in (0xEE,0xE4,0xC9)
        writer_slot=tags['ik1302'][1][0]
        before=state['ik1302'];j,emitted=step(state,tags,j,pins,p)
        if code in (0xE7,0xA8):
            writes.append((code,writer_slot))
            print('CONDITIONAL later writer',f'{code:02X}',writer_slot,
                  'last-high F' if marker_payload else 'last-high notF',flush=True)
    else:raise AssertionError('bounded conditional continuation not completed')
    final_ring=ring(state,tags)
    entered=[q['N4'](int(k==7)) for k in range(12)]
    w['prove'](p,w['eq'](final_ring['X'][1:36:3],entered),
               f'conditional last-high {"F" if marker_payload else "notF"}: cache OVERWRITTEN by digit1 in X before35')
    w['prove'](p,w['eq']([v for slot in slots for k,v in enumerate(final_ring[slot]) if k%3==2],
                       [v for slot in slots for k,v in enumerate(initial_ring[slot]) if k%3==2]),
               'all program-lane pages still held through conditional return35')
    # Record SEMANTIC dependence, not just free variables in an expression:
    # payload5 remains syntactically symbolic when constrained to F.
    assert p.check()==sat
    sample=p.model()
    remaining=[]
    def dependent(value):
        if not get_vars(value):return False
        p.push();p.add(value!=sample.eval(value,model_completion=True))
        answer=p.check();p.pop()
        assert answer in (sat,q['unsat'])
        return answer==sat
    for name in models:
        for field in ('r','st','s','s1','l','t','carry'):
            values=getattr(state[name],field)
            if not isinstance(values,list):values=[values]
            for k,value in enumerate(values):
                if dependent(value):remaining.append((name,field,k))
    for slot,values in final_ring.items():
        for k,value in enumerate(values):
            if dependent(value):remaining.append(('ring',slot,k))
    for name,fields in state['_wire'].items():
        for field,value in fields.items():
            if dependent(value):remaining.append((name,field,0))
    expected=[('ring','Y',k) for k in program[:5 if marker_payload else 6]]
    assert remaining==expected,('new surviving reserve requires investigation',remaining)
    w['prove'](p,w['eq']([final_ring['Y'][k] for k in program],payload),
               'all surviving payload tetras are exactly the ORIGINAL program page, no new copy')
    constants={}
    for name in models:
        for field in ('r','st','s','s1','l','t','carry'):
            values=getattr(state[name],field)
            if not isinstance(values,list):values=[values]
            for k,value in enumerate(values):
                constants[f'{name}.{field}[{k}]']=sample.eval(value,model_completion=True).as_long()
    for slot in slots:
        for k,value in enumerate(final_ring[slot]):
            if slot!='Y' or k not in program:
                constants[f'ring.{slot}[{k}]']=sample.eval(value,model_completion=True).as_long()
    for name in names:
        for field in ('input','output'):
            constants[f'{name}.{field}']=sample.eval(state['_wire'][name][field],model_completion=True).as_long()
    print('CONDITIONAL payload-dependent fields at return35:',remaining,flush=True)
    print('CONDITIONAL return35 after fixed key release',len(sequence)-1,'macros; writes',writes,
          '; last-high F',marker_payload,'; NOT native success.',flush=True)
    return constants


if __name__=='__main__':
    if '--continuation-only' not in sys.argv:
        validate_baseline()
        conditional_first_export()
    nonmarker=conditional_later_export(False)
    marker=conditional_later_export(True)
    assert nonmarker.keys()==marker.keys()
    differences={field:(nonmarker[field],marker[field]) for field in nonmarker
                 if nonmarker[field]!=marker[field]}
    print('CONDITIONAL last-high F/notF side effects at35:',differences,flush=True)
    print('PASS: both cases cover ALL256^3. Within each case complete working/ring/interface '
          'state at35 varies ONLY in the original program tetras. Across cases '
          'a marker predicate may survive, NOT an injective three-byte reserve. '
          'No native partial K2 and no global exclusion.',flush=True)
