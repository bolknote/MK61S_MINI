"""Bounded ARM float/FMA qualification, full raw records and honest limits."""
import argparse,collections,gzip,hashlib,json,struct,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(W/'support'))
import native_eabi_m0_arm_self_test as arm
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
from oracles import (DirectMPFR,decode,equal,is_nan,integer_binary,integer_cast,
                     integer_fma,integer_sqrt,round_ratio,comparison,float_integer)
import corpora

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
ELF=W/'fixture.elf';RESIDENT=P/'firmware/mk61s-picocalc-pico-h.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
REFERENCE=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
STATES=[struct.pack('<7I',17,3,17,3,5,2,1),
        struct.pack('<7I',0x80000001,7,0x80000001,7,0xedb6db6e,0xffffffff,3),
        struct.pack('<7I',0xfedcba98,0x76543210,0xfedcba98,0x76543210,0x11223344,0x55667788,2)]

class QMachine(arm.Machine):
    def __init__(self,*args,**kw):
        self.sio_writes=0
        super().__init__(*args,**kw)
        self.sio_writes=0
    def write(self,uc,access,address,size,value,user):
        if 0xd0000060<=address<0xd000007c:self.sio_writes+=1
        return super().write(uc,access,address,size,value,user)


def coverage(arguments,width):
    f=23 if width==32 else 52;emask=255 if width==32 else 2047
    exps=set();subwidths=set();signs=set();categories=collections.Counter()
    for row in arguments:
        for a in row:
            mag=a&((1<<(width-1))-1);e=(mag>>f)&emask;frac=mag&((1<<f)-1)
            exps.add(e);signs.add(a>>(width-1))
            if e==0 and frac:subwidths.add(frac.bit_length())
            categories['nan' if e==emask and frac else 'infinity' if e==emask else 'subnormal' if e==0 and frac else 'zero' if e==0 else 'normal']+=1
    return dict(input_exponent_fields=sorted(exps),subnormal_significand_widths=sorted(subwidths),signs=sorted(signs),input_categories=dict(categories))


def reference_map(op):
    return {'add':'qfp_fadd','sub':'qfp_fsub','frsub':'qfp_fsub','mul':'qfp_fmul','div':'qfp_fdiv',
            'sqrt':'qfp_fsqrt','i2f':'qfp_int2float','ui2f':'qfp_uint2float','f2iz':'qfp_float2int',
            'f2uiz':'qfp_float2uint','f2d':'qfp_float2double','d2f':'qfp_double2float'}.get(op)


def run_operation(mode,op,symbol,inputs,width,rw,oracle,machine,reference,resident=None):
    begin=time.monotonic();digest=hashlib.sha256();failures=[];wrong=oracle_errors=resident_errors=0
    valid=outside=0;sp_low=arm.SP;written_low=arm.SP
    speed=[];sampled=set(range(0,len(inputs),max(1,len(inputs)//256)))
    if len(sampled)>256:sampled=set(sorted(sampled)[:256])
    spy=set(sorted(sampled)[:16]);stack_trace_low=[arm.SP]
    filename=mode+'-'+op+'.records.bin.gz'
    with (W/filename).open('wb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as archive:
        for i,args in enumerate(inputs):
            if mode=='fma':
                exact=integer_fma(*args);mpfr=oracle.fma(*args);args3=args
            elif op in ('add','sub','frsub','mul','div'):
                exact=integer_binary(op,*args);mpfr=oracle.float(op,*args);args3=(*args,0)
            elif op.startswith('cmp'):
                value=comparison(*args)
                pred={'cmpeq':value==0,'cmplt':value==-1,'cmple':value<=0,'cmpge':value in (0,1),'cmpgt':value==1,'cmpun':value==2}
                exact=int(pred[op]);mpfr=exact;args3=(*args,0)
            elif op in ('f2iz','f2uiz'):
                exact,in_domain=float_integer(args[0],op=='f2iz');valid+=in_domain;outside+=not in_domain
                mpfr=exact;args3=(*args,0,0)
            elif op in ('i2f','ui2f'):
                a=args[0];integer=a-(1<<32) if op=='i2f' and a>>31 else a
                exact=round_ratio(abs(integer),1,0,32,integer<0);mpfr=oracle.float(op,*args);args3=(*args,0,0)
            else:
                exact=integer_sqrt(args[0]) if op=='sqrt' else integer_cast(args[0],width,rw)
                mpfr=oracle.float(op,*args);args3=(*args,0,0)
            numeric=not(op.startswith('cmp') or op in ('f2iz','f2uiz'))
            oracle_same=equal(mpfr,exact,rw) if numeric else mpfr==exact
            oracle_errors+=not oracle_same
            state=STATES[i%3];machine.uc.mem_write(0xd0000060,state)
            machine.stack_lowest=arm.SP
            def trace(uc,*unused):stack_trace_low[0]=min(stack_trace_low[0],uc.reg_read(UC_ARM_REG_SP))
            hook=machine.uc.hook_add(UC_HOOK_CODE,trace) if i in spy else None
            if hook is not None:machine.uc.ctl_flush_tb()
            try:
                got,_,instructions=machine.call(symbol,args[0],args[1] if len(args)>1 else 0,width=width,count=i in sampled,c=args[2] if len(args)==3 else None)
            finally:
                if hook is not None:machine.uc.hook_del(hook);machine.uc.ctl_flush_tb()
            got&=(1<<rw)-1
            assert bytes(machine.uc.mem_read(0xd0000060,28))==state,(op,i,'SIO context changed',args)
            written_low=min(written_low,machine.stack_lowest)
            good=equal(got,exact,rw) if numeric else got==exact
            wrong+=not good
            if not good or not oracle_same:
                item=dict(index=i,arguments=[f'{a:016X}' for a in args],actual=f'{got:016X}',integer_oracle=f'{exact:016X}',mpfr_oracle=f'{mpfr:016X}',oracle_agree=oracle_same)
                failures.append(item)
                with (W/(mode+'-failures.jsonl')).open('a') as log:log.write(json.dumps(dict(operation=op,**item))+'\n')
            if resident is not None:
                resident.uc.mem_write(0xd0000060,state);resident.stack_lowest=arm.SP
                rg=resident.call(symbol,args[0],args[1],c=args[2])[0]
                assert bytes(resident.uc.mem_read(0xd0000060,28))==state,('resident SIO',i)
                resident_errors+=rg!=got
            if i in sampled:
                row=dict(index=i,arguments=[f'{a:016X}' for a in args],own_result=f'{got:016X}',expected=f'{exact:016X}',own_instructions=instructions,owned_correct=good)
                qsymbol=reference_map(op)
                if qsymbol is not None and qsymbol in reference.elf.symbols:
                    qargs=args[::-1] if op=='frsub' else args
                    qgot,_,qcount=reference.call(qsymbol,qargs[0],qargs[1] if len(qargs)>1 else 0,width=width,count=True)
                    qgot&=(1<<rw)-1
                    row.update(reference_symbol=qsymbol,reference_result=f'{qgot:016X}',reference_instructions=qcount,
                               reference_correct=equal(qgot,exact,rw) if numeric else qgot==exact)
                else:row['reference_gap']='No native FMA or matching boolean-predicate ABI baseline in this packet'
                speed.append(row)
            packed=struct.pack('<6Q',*args3,got,exact,mpfr);archive.write(packed);digest.update(packed)
            if (i+1)%10000==0:print(mode,op,i+1,'/',len(inputs),'wrong',wrong,'oracle disagreements',oracle_errors,flush=True)
    both=[r for r in speed if r['owned_correct'] and r.get('reference_correct')]
    allq=[r for r in speed if 'reference_instructions' in r]
    result=dict(status='PASS' if not(wrong or oracle_errors or resident_errors) else 'FAIL',symbol=symbol,cases=len(inputs),wrong_rounding_or_value=wrong,
        MPFR_integer_disagreements=oracle_errors,resident_fixture_raw_mismatches=resident_errors,
        full_raw_records=filename,record_format='little-endian6Q: a,b,c,actual,exact_integer_oracle,MPFR_oracle; unused b/c are0',
        uncompressed_sha256=digest.hexdigest(),records_sha256=sha(W/filename),result_width=rw,input_ABI_width=width,
        coverage=coverage(inputs,width) if op not in ('i2f','ui2f') else dict(integer_width=32,bit_lengths=sorted({a[0].bit_length() for a in inputs})),
        integer_conversion_valid_cases=valid,integer_conversion_outside_valid_range_policy_cases=outside,
        maximum_written_stack_bytes=arm.SP-written_low,SP_instrumented_sample_calls=len(spy),maximum_sampled_SP_depth=arm.SP-stack_trace_low[0],
        ABI='R4-R11 and restored SP checked every call; all writes bounded by4096 stack bytes; FMA third arg at caller SP is not counted as a callee allocation',
        SIO_context_states_preserved_each_call=['READY clean','READY DIRTY','pending DIRTY'],failures=failures,
        instruction_sample=speed,sampled_both_correct_cases=len(both),sampled_both_correct_own_slower=sum(r['own_instructions']>r['reference_instructions'] for r in both),
        raw_instruction_sample_means=dict(own=sum(r['own_instructions'] for r in allq)/len(allq) if allq else None,reference=sum(r['reference_instructions'] for r in allq)/len(allq) if allq else None),
        correct_instruction_sample_means=dict(own=sum(r['own_instructions'] for r in both)/len(both) if both else None,reference=sum(r['reference_instructions'] for r in both)/len(both) if both else None),
        seconds=time.monotonic()-begin)
    print('COMPLETE',mode,op,len(inputs),result['status'],'wrong',wrong,'oracle',oracle_errors,'written stack',result['maximum_written_stack_bytes'],flush=True)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['float','fma'],required=True);a=parser.parse_args()
    for n in [a.mode+'-failures.jsonl']:
        assert not (W/n).exists(),'Existing failure evidence must not be overwritten'
    hashes={str(p.relative_to(ROOT)):sha(p) for p in [ELF,RESIDENT,ROM,REFERENCE]}
    producer_pins={n:sha(W/n) for n in ['qualify.py','oracles.py','corpora.py']}
    support_pins=json.loads((W/'body-audit.json').read_text())['support_pins']
    assert all(sha(W/n)==d for n,d in support_pins.items())
    m=QMachine(ELF,True,stack_bytes=4096,bootrom=ROM)
    resident=QMachine(RESIDENT,True,stack_bytes=4096,bootrom=ROM) if a.mode=='fma' else None
    q=arm.Machine(REFERENCE,True,stack_bytes=4096);oracle=DirectMPFR();reports={}
    if a.mode=='float':
        pairs=corpora.float_pairs();values=corpora.float_values()
        jobs=[(op,'__aeabi_f'+op,pairs,32,32) for op in ['add','sub','frsub','mul','div']]
        jobs += [(op,'__aeabi_f'+op,pairs,32,32) for op in ['cmpeq','cmplt','cmple','cmpge','cmpgt','cmpun']]
        jobs += [('f2iz','__aeabi_f2iz',[(v,) for v in values],32,32),('f2uiz','__aeabi_f2uiz',[(v,) for v in values],32,32)]
        jobs += [(op,'__aeabi_'+op,[(v,) for v in corpora.integer_values()],32,32) for op in ['i2f','ui2f']]
        jobs += [('f2d','__aeabi_f2d',[(v,) for v in values],32,64),('d2f','__aeabi_d2f',[(v,) for v in corpora.double_values()],64,32),('sqrt','mk61_m0_sqrtf',[(v,) for v in corpora.sqrt_values()],32,32)]
    else:jobs=[('fma','mk61_m0_fma',corpora.fma_triples(),64,64)]
    for op,symbol,inputs,width,rw in jobs:
        reports[op]=run_operation(a.mode,op,symbol,inputs,width,rw,oracle,m,q,resident)
        (W/(a.mode+'-progress.json')).write_text(json.dumps(dict(operations=reports,complete=False),indent=2)+'\n')
    assert hashes=={str(p.relative_to(ROOT)):sha(p) for p in [ELF,RESIDENT,ROM,REFERENCE]}
    assert producer_pins=={n:sha(W/n) for n in producer_pins}
    result=dict(status='PASS_FINITE_ARM_QUALIFICATION' if all(r['status']=='PASS' for r in reports.values()) else 'FAIL',
        mode=a.mode,operations=reports,actual_public_calls=sum(r['cases'] for r in reports.values()),
        resident_public_calls=sum(r['cases'] for r in reports.values()) if resident else 0,
        ROM_initializers=m.rom_initializers,ROM_intrinsic_models=m.rom_models,MPFR_version=oracle.version,
        maximum_float_MPFR_precision=oracle.max_precision,FMA_MPFR_precision_counts=oracle.fma_precision_counts,
        SIO_write_attempts=m.sio_writes,resident_SIO_write_attempts=resident.sio_writes if resident else None,
        input_pins=hashes,producer_pins=producer_pins,support_pins=support_pins,
        limits=['Finite deterministic coverage, not exhaustive all32/64-bit inputs or an all-input proof',
                'RNE return values; errno/fenv exception flags and other rounding modes are outside runtime contract',
                'Integer conversion outside representable result range tests declared saturating/NaN policy separately from valid-range correctness',
                'SP depths instrumented on selected16 calls per entry; bounded writes/restored SP checked every call',
                'Instruction samples are diagnostics with full adverse inputs retained, not physical cycle or universal speed acceptance',
                'No native Qfplib FMA; unfused composition is not substituted'],
        resident_changed=False,canonical_changed=False,hardware_accessed=False,goal_complete=False)
    (W/(a.mode+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('FINAL',a.mode,result['status'],'public calls',result['actual_public_calls'],'resident calls',result['resident_public_calls'],flush=True)
    assert result['status'].startswith('PASS')

if __name__=='__main__':main()
