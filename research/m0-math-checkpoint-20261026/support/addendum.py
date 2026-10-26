"""Fill measured subnormal-width gaps and trace SP on explicit stack vectors."""
import hashlib,json,struct
from pathlib import Path
import qualify as q
from oracles import DirectMPFR,equal
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_SP
W=Path(__file__).resolve().parent;OUT=W/'addendum';OUT.mkdir(exist_ok=True)
q.W=OUT

def unique(rows):return list(dict.fromkeys(rows))

def main():
    producer=q.sha(Path(__file__))
    m=q.QMachine(q.ELF,True,stack_bytes=4096,bootrom=q.ROM)
    resident=q.QMachine(q.RESIDENT,True,stack_bytes=4096,bootrom=q.ROM)
    reference=q.arm.Machine(q.REFERENCE,True,stack_bytes=4096);oracle=DirectMPFR()
    pairs=[]
    for width in range(1,24):
        for delta in [-1,0,1]:
            a=min(0x7fffff,max(1,(1<<(width-1))+delta))
            for b in [0,1,1<<(width-1),1<<(23-width),0x7fffff,0x800000,0x3f000000,0x3f800000,0x40000000]:
                pairs.extend([(a,b),(a|0x80000000,b),(a,b|0x80000000),(a|0x80000000,b|0x80000000)])
        for d in [-1,0,1]:pairs.append((0x800000+d,(127+width)<<23))
    pairs=unique(pairs)
    reports={}
    for op in ['add','sub','frsub','mul','div']:
        symbol='__aeabi_'+('frsub' if op=='frsub' else 'f'+op)
        reports[op]=q.run_operation('float',op,symbol,pairs,32,32,oracle,m,reference)
        assert reports[op]['coverage']['subnormal_significand_widths']==list(range(1,24))
    double_values=unique([(min(0xfffffffffffff,max(1,(1<<(width-1))+d))|s,) for width in range(1,53) for d in [-1,0,1] for s in [0,1<<63]])
    reports['d2f']=q.run_operation('float','d2f','__aeabi_d2f',double_values,64,32,oracle,m,reference)
    assert reports['d2f']['coverage']['subnormal_significand_widths']==list(range(1,53))
    triples=[];one=0x3ff0000000000000;sign=1<<63
    for width in range(1,53):
        for delta in [-1,0,1]:
            a=min(0xfffffffffffff,max(1,(1<<(width-1))+delta))
            for b,c in [(one,0),(one,a),(one,a^sign),(one+1,1),(one-1,a),
                        (0x3fe0000000000000,a),(0x10000000000000,0),(0x7fefffffffffffff,a)]:
                triples.extend([(a,b,c),(a|sign,b,c),(a,b|sign,c),(a,b,c^sign)])
    triples=unique(triples)
    reports['fma']=q.run_operation('fma','fma','mk61_m0_fma',triples,64,64,oracle,m,reference,resident)
    assert reports['fma']['coverage']['subnormal_significand_widths']==list(range(1,53))
    # Trace actual SP at every instruction on a bounded set of representative
    # and longest instruction-sample vectors, without oracle output slots.
    base_float=json.loads((W/'float.json').read_text());base_fma=json.loads((W/'fma.json').read_text())
    probes=[]
    for name,r in {**base_float['operations'],'fma':base_fma['operations']['fma']}.items():
        selected=sorted(r['instruction_sample'],key=lambda x:x['own_instructions'],reverse=True)[:4]
        selected+=r['instruction_sample'][:4]+r['instruction_sample'][-4:]
        seen=set()
        for sample in selected:
            args=tuple(int(v,16) for v in sample['arguments'])
            if args in seen:continue
            seen.add(args);low=[q.arm.SP];m.stack_lowest=q.arm.SP
            state=q.STATES[len(probes)%3];m.uc.mem_write(0xd0000060,state)
            def trace(uc,*unused):
                sp=uc.reg_read(UC_ARM_REG_SP)
                assert q.arm.SP-4096<=sp<=q.arm.SP and not sp&3,(name,'SP bound/alignment',hex(sp))
                low[0]=min(low[0],sp)
            hook=m.uc.hook_add(UC_HOOK_CODE,trace);m.uc.ctl_flush_tb()
            try:got=m.call(r['symbol'],args[0],args[1] if len(args)>1 else 0,width=r['input_ABI_width'],c=args[2] if len(args)==3 else None)[0]&((1<<r['result_width'])-1)
            finally:m.uc.hook_del(hook);m.uc.ctl_flush_tb()
            expected=int(sample['expected'],16)
            assert equal(got,expected,r['result_width']) if name not in ['cmpeq','cmplt','cmple','cmpge','cmpgt','cmpun','f2iz','f2uiz'] else got==expected
            assert bytes(m.uc.mem_read(0xd0000060,28))==state
            probes.append(dict(operation=name,symbol=r['symbol'],arguments=sample['arguments'],actual=f'{got:016X}',expected=sample['expected'],SP_depth=q.arm.SP-low[0],written_stack_bytes=q.arm.SP-m.stack_lowest))
    assert q.sha(Path(__file__))==producer
    result=dict(status='PASS_BOUNDED_WIDTH_AND_STACK_ADDENDUM',operations=reports,
        actual_public_calls=sum(r['cases'] for r in reports.values()),resident_FMA_calls=len(triples),
        full_instruction_SP_probes=probes,maximum_probed_SP_depth=max(r['SP_depth'] for r in probes),
        maximum_probed_written_stack_bytes=max(r['written_stack_bytes'] for r in probes),
        FMA_MPFR_precision_counts=oracle.fma_precision_counts,MPFR_version=oracle.version,
        producer_sha256=producer,shared_producer_pins={n:q.sha(W/n) for n in ['qualify.py','oracles.py','corpora.py']},
        fixture_sha256=q.sha(q.ELF),resident_sha256=q.sha(q.RESIDENT),SIO_writes=m.sio_writes,resident_SIO_writes=resident.sio_writes,
        scope='Explicit all23 binary32 and52 binary64 subnormal input widths; finite mantissas/signs, not exhaustive inputs. Selected vectors trace every instruction; all qualification calls check restored SP/registers and bounded stack writes.',
        source_changed=False,resident_changed=False,hardware_accessed=False,goal_complete=False)
    assert all(r['status']=='PASS' for r in reports.values())
    (W/'addendum.json').write_text(json.dumps(result,indent=2)+'\n')
    print('FINAL addendum PASS;fixture calls',result['actual_public_calls'],'resident',len(triples),'SP probes',len(probes),flush=True)

if __name__=='__main__':main()
