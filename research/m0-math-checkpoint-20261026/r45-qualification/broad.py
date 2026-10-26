"""Replay all 119 original chunks and 53 independent groups on one ELF."""
from pathlib import Path
from collections import Counter
import ctypes as C
import gzip
import hashlib
import importlib.util
import json
import struct
import sys
import time

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
U = ROOT / '.build/m0-math-unified-ddiv-cold-overflow-r45-20261026'
Q = ROOT / '.build/m0-float-fma-qualification-20261023'
sys.path[:0] = [str(Q), str(Q / 'support'), str(ROOT / 'tests')]
from m0_mpfr_oracle import Oracle, _Number
from oracles import DirectMPFR, equal, round_ratio, integer_cast
from native_eabi_m0_arm_self_test import Machine, SP
spec = importlib.util.spec_from_file_location('broad_unified_machine', U / 'harness.py')
unified = importlib.util.module_from_spec(spec)
spec.loader.exec_module(unified)
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(U/'FROZEN.json')=='dbc455078837507acaeb750df1e3fb6800b923e2a9a880c9c6bcc2150ba3527a'
assert not (W / 'broad.json').exists() and not (W / 'broad-records.jsonl.gz').exists()
benchmark_path = ROOT / '.build/m0-balanced-timing-v87-20261022/benchmark.json'
independent_path = ROOT / '.build/m0-asin-scaled-bound-v164-20261023/result.json'
benchmark = json.loads(benchmark_path.read_bytes())
independent = json.loads(independent_path.read_bytes())
jobs, mappings, pins = [], {}, {}
for s in benchmark['chunks']:
    mappings.setdefault(s['operation'], (s['own_symbol'], s['qfplib_symbol']))
    p = Path(s['input'])
    assert sha(p) == s['input_sha256']
    pins[str(p.relative_to(ROOT))] = sha(p)
    vectors = list(struct.iter_unpack('<3Q', p.read_bytes()[32:]))
    assert len(vectors) == s['cases']
    for i, (x, y, expected) in enumerate(vectors):
        jobs.append(dict(origin='original119', group=s['stream'], chunk=s['index'], index=i,
                         operation=s['operation'], x=x, y=y, expected=expected, historical_reference=s['qfplib_symbol']))
for group in independent['groups']:
    for i, r in enumerate(group['rows']):
        op = group['operation']
        ref = mappings[op][1]
        if op == 'pow':
            ref = ('qfp_composed_pow_exact' if group['stream'] == 'composed_exact_exponents' else
                   'qfp_composed_pow_integer' if group['stream'].startswith('composed_negative_') else 'qfp_composed_pow')
        jobs.append(dict(origin='independent53', group=group['stream'], index=i, operation=op,
                         x=int(r['x'], 16), y=int(r['y'], 16), expected=int(r['expected'], 16), historical_reference=ref))
assert len(benchmark['chunks']) == 119 and len(independent['groups']) == 53 and len(jobs) == 30136
REF = ROOT / '.build/m0-v138-execution-20261023/reference/reference.elf'
assert sha(REF) == 'b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
machines = {label:unified.machine(label) for label in ['candidate','zero-control']}
machines['Qfplib'] = Machine(REF, True)
assert all(not m.rom_models for m in machines.values())
pow_refs = ['qfp_composed_pow','qfp_composed_pow_exact','qfp_composed_pow_integer']
for op, (own, ref) in mappings.items():
    assert all(own in machines[label].elf.symbols for label in ['candidate','zero-control']), own
    assert all(name in machines['Qfplib'].elf.symbols for name in (pow_refs if op=='pow' else [ref])), ref
states = {'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
oracle, float_oracle = Oracle(), DirectMPFR()
lib = oracle.lib
pointer = C.POINTER(_Number)
for name in ['mpfr_set_si','mpfr_set_ui']:
    getattr(lib,name).argtypes=[pointer,C.c_long if name.endswith('_si') else C.c_ulong,C.c_int]
lib.mpfr_get_si.argtypes=[pointer,C.c_int];lib.mpfr_get_si.restype=C.c_long
lib.mpfr_get_ui.argtypes=[pointer,C.c_int];lib.mpfr_get_ui.restype=C.c_ulong
lib.mpfr_cmp.argtypes=[pointer,pointer];lib.mpfr_cmp.restype=C.c_int
numbers=[_Number(),_Number()]
for n in numbers:lib.mpfr_init2(C.byref(n),64)
oracle_counts=Counter()
isnan=lambda x:(x&0x7fffffffffffffff)>0x7ff0000000000000


def reference(op,x,y):
    n=numbers[0]
    if op in ['i2d','ui2d','l2d','ul2d']:
        signed=op in ['i2d','l2d'];width=32 if op in ['i2d','ui2d'] else 64
        value=x&((1<<width)-1)
        if signed and value>>(width-1):value-=1<<width
        setter=lib.mpfr_set_si if signed else lib.mpfr_set_ui
        setter(C.byref(n),value,0)
        got=struct.unpack('<Q',struct.pack('<d',lib.mpfr_get_d(C.byref(n),0)))[0]
        exact=round_ratio(abs(value),1,0,64,value<0)
        assert got==exact
        oracle_counts['integer_to_double_MPFR_and_exact']+=1
        return got,64
    if op in ['d2iz','d2uiz','d2lz','d2ulz']:
        signed=op in ['d2iz','d2lz'];width=32 if op in ['d2iz','d2uiz'] else 64
        e,f=(x>>52)&2047,x&((1<<52)-1)
        lo,hi=(-(1<<(width-1)),(1<<(width-1))-1) if signed else (0,(1<<width)-1)
        if e==2047:
            value=0 if f else lo if x>>63 else hi
        elif e<1023:value=0
        else:
            magnitude=((1<<52)|f)
            magnitude=magnitude<<(e-1075) if e>=1075 else magnitude>>(1075-e)
            value=max(lo,min(hi,-magnitude if x>>63 else magnitude))
        lib.mpfr_set_d(C.byref(n),struct.unpack('<d',struct.pack('<Q',x))[0],0)
        mpfr=int((lib.mpfr_get_si if signed else lib.mpfr_get_ui)(C.byref(n),1))
        mpfr=max(lo,min(hi,mpfr))
        assert mpfr==value,(op,hex(x),mpfr,value)
        oracle_counts['double_to_integer_MPFR_and_exact']+=1
        return value&((1<<width)-1),width
    if op in ['f2d','d2f']:
        sw,rw=(32,64) if op=='f2d' else (64,32)
        a=x&((1<<sw)-1)
        expected=float_oracle.float(op,a);exact=integer_cast(a,sw,rw)
        assert equal(expected,exact,rw)
        mag=a&((1<<(sw-1))-1);inf=0x7f800000 if sw==32 else 0x7ff0000000000000
        oracle_counts['cast_NaN_policy_shortcuts' if mag>inf else 'float_cast_directed_MPFR_and_exact']+=1
        return expected,rw
    if op.startswith('dcmp'):
        unordered=isnan(x) or isnan(y)
        if unordered:cmp=0
        else:
            for n,a in zip(numbers,[x,y]):
                lib.mpfr_set_d(C.byref(n),struct.unpack('<d',struct.pack('<Q',a))[0],0)
            cmp=lib.mpfr_cmp(*map(C.byref,numbers))
        values={'dcmpeq':not unordered and cmp==0,'dcmplt':not unordered and cmp<0,
                'dcmple':not unordered and cmp<=0,'dcmpge':not unordered and cmp>=0,'dcmpgt':not unordered and cmp>0}
        oracle_counts['comparison_exact_MPFR_inputs' if not unordered else 'comparison_unordered_policy']+=1
        return int(values[op]),32
    args=[x,y] if op in ['pow','dadd','dsub','dmul','ddiv'] else [x]
    shortcut=any(isnan(a) and not a&(1<<51) for a in args)
    expected=oracle.reference(op,*args)
    oracle_counts['sNaN_policy_shortcuts' if shortcut else 'binary64_directed_MPFR_inputs']+=1
    return expected,64


for p in [benchmark_path,independent_path,REF,U/'candidate.elf',U/'zero-control.elf',U/'link-result.json',
          U/'loader-layout-proof.json',U/'private-return-proof.json',U/'harness.py',unified.ROM,
          Q/'oracles.py',Q/'support/m0_mpfr_oracle.py',Q/'support/native_eabi_m0_arm_self_test.py',Path(__file__)]:
    pins[str(p.relative_to(ROOT))]=sha(p)
(W/'broad-source-pins.json').write_text(json.dumps(dict(files=pins),indent=2)+'\n')
completed,attempted=Counter(),Counter()
group_counts={};case_classification=Counter();remaining=[];current=None;row_count=0
started=time.monotonic()
try:
    with gzip.GzipFile(filename=str(W/'broad-records.jsonl.gz'),mode='wb',mtime=0) as stream:
        for index,job in enumerate(jobs):
            current=dict(case=index,**job)
            if index%256==0:print('unified-broad',index,'/',len(jobs),round(time.monotonic()-started,1),flush=True)
            op,x,y=job['operation'],job['x'],job['y']
            expected,rw=reference(op,x,y)
            assert equal(expected,job['expected'],rw),('historical expected disagrees',current,hex(expected))
            own,ref=mappings[op];refs=pow_refs if op=='pow' else [ref]
            case_relations=[]
            key=job['origin']+'/'+op+'/'+job['group']
            stats=group_counts.setdefault(key,dict(cases=0,states=0,correct_comparison=Counter(),wrong_reference_outputs_retained=0,
                candidate_minus_control_deltas=Counter(),loss_cases=0))
            stats['cases']+=1
            for state_name,sio in states.items():
                outputs,counts,correct={},{},{}
                for label in ['candidate','zero-control',*refs]:
                    m=machines[label if label in machines else 'Qfplib']
                    m.uc.mem_write(0xd0000060,sio);attempted[label]+=1
                    got,_,cost=m.call(own if label in ['candidate','zero-control'] else label,x,y,count=True)
                    completed[label]+=1;got&=(1<<rw)-1
                    after=bytes(m.uc.mem_read(0xd0000060,28))
                    if state_name=='DIRTY':assert after==sio,(label,'DIRTY SIO',current)
                    else:assert not struct.unpack('<7I',after)[6]&2,(label,'READY SIO',current)
                    outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,rw)
                    if label in ['candidate','zero-control']:
                        assert correct[label],('wrong unified output',label,current,outputs[label],f'{expected:016X}')
                assert outputs['candidate']==outputs['zero-control']
                comparisons=[]
                for q in refs:
                    if not correct[q]:stats['wrong_reference_outputs_retained']+=1;continue
                    c,r=counts['candidate'],counts[q]
                    relation='faster' if c<r else 'equal' if c==r else 'slower'
                    stats['correct_comparison'][relation]+=1;comparisons.append(relation)
                    if relation=='slower':remaining.append(dict(case=index,operation=op,origin=job['origin'],group=job['group'],
                        x=f'{x:016X}',y=f'{y:016X}',SIO=state_name,reference=q,candidate=c,Qfplib=r))
                case_relations+=comparisons;stats['states']+=1
                stats['candidate_minus_control_deltas'][counts['candidate']-counts['zero-control']]+=1
                row=dict(case=index,**{k:v for k,v in job.items() if k not in ['x','y','expected']},
                    x=f'{x:016X}',y=f'{y:016X}',SIO=state_name,expected=f'{expected:016X}',result_width=rw,
                    outputs=outputs,instructions=counts,correct=correct)
                stream.write((json.dumps(row,separators=(',',':'))+'\n').encode());row_count+=1
            classification='slower' if 'slower' in case_relations else 'equal' if 'equal' in case_relations else 'strict' if case_relations else 'no_correct_reference'
            case_classification[classification]+=1;stats['loss_cases']+=classification=='slower'
except Exception as error:
    (W/'broad-FAILURE.json').write_text(json.dumps(dict(status='FAILED_BROAD_UNIFIED_ATTEMPT',error=repr(error),current=current,
        completed_ARM_calls=dict(completed),attempted_ARM_calls=dict(attempted),partial_ARM_calls=sum(attempted.values())-sum(completed.values()),
        oracle_input_evaluations=dict(oracle_counts),completed_state_rows=row_count,hardware_accessed=False,goal_complete=False),indent=2)+'\n')
    raise
finally:
    for n in numbers:lib.mpfr_clear(C.byref(n))
assert row_count==2*len(jobs)
result=dict(status='PASS_SINGLE_ELF_ORIGINAL119_AND_INDEPENDENT53_RNE_AND_INSTRUCTIONS',
    candidate_ELF_sha256=sha(U/'candidate.elf'),zero_control_ELF_sha256=sha(U/'zero-control.elf'),reference_ELF_sha256=sha(REF),
    raw_records_sha256=sha(W/'broad-records.jsonl.gz'),case_evaluations=len(jobs),case_overlap_not_deduplicated=True,
    original119_cases=23352,independent53_cases=6784,state_rows=row_count,candidate_wrong=0,zero_control_wrong=0,
    actual_qualified_math_ARM_calls=sum(completed.values()),completed_ARM_calls=dict(completed),oracle_input_evaluations=dict(oracle_counts),
    automatic_ROM_lookup_initializations_excluded=2,explicit_source_loader_calls_excluded=2,MPFR_version=oracle.version,
    all_case_classification=dict(case_classification),groups=group_counts,remaining=remaining,
    observed_stacks={name:SP-m.stack_lowest for name,m in machines.items()},
    no_old_firmware_or_component_overlays_loaded=True,all_correct_references_compared=True,
    all_incorrect_reference_outputs_and_costs_retained=True,no_nominal_reference_domain_filter=True,
    PCS_SP_bounded_writes_and_SIO_checked_every_call=True,instructions_are_not_physical_cycles=True,
    expanded_component_regressions_and_totality_pending=True,integration_GO=False,hardware_accessed=False,goal_complete=False,
    elapsed_seconds=time.monotonic()-started)
(W/'broad.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['groups','remaining']},indent=2),flush=True)
