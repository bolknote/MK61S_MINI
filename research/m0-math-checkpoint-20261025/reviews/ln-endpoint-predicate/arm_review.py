"""Compact actual ARM endpoint/wrap and public dispatch/MPFR checks only."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
D=Path(__file__).resolve().parent
ROOT=D.parents[1]
W=ROOT/'.build/m0-ln-endpoint-predicate-20261024'
V=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
SUP=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(SUP.parent),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
get=lambda p:json.loads(Path(p).read_text())


def put(name,obj):
    with (D/name).open('x') as file:
        json.dump(obj,file,indent=2)
        file.write('\n')


def main():
    assert sha(W/'candidate.elf')=='5187e1bbba29ec6b0d24cfc57aba9feb74598cc0b8df0df06fe6b13a53039e7e'
    assert sha(D/'candidate.elf')==sha(W/'candidate.elf')
    proof=get(D/'SOURCE-WHOLE-ELF-PROOF.json')
    capsule=(D/'product46-capsule.bin').read_bytes()
    assert hashlib.sha256(capsule).hexdigest()=='75729579767fb4b3269141b6c62b1ae4fad49ed8817158b0e7d4bedcc717ecc8'
    seed=int(proof['retained_seed_capsule']['address'],16)
    states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),
            'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
    bare={};sio=[];codecalls={}
    for label,path in [('parent',W/'control.elf'),('candidate',D/'candidate.elf')]:
        m=Machine(path,True,stack_bytes=128)
        m.uc.mem_write(seed,capsule)
        ranges=[(s[3],s[3]+s[5]) for s in m.elf.sections if s[2]&2 and s[5]]+[(seed,seed+184)]
        def access(uc,kind,address,size,value,user,label=label,ranges=ranges):
            if 0xd0000060<=address<0xd000007c:
                sio.append((label,address,size))
                raise AssertionError('bare helper touched SIO')
            assert SP-128<=address and address+size<=SP or any(a<=address and address+size<=z for a,z in ranges),(label,hex(address),size)
        def code(uc,address,size,user,label=label,ranges=ranges):
            assert any(a<=address and address+size<=z for a,z in ranges),(label,'unexpected code',hex(address))
            codecalls[label]=codecalls.get(label,0)+1
        m.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,access)
        m.uc.hook_add(UC_HOOK_CODE,code)
        bare[label]=m
    # New predicate boundaries only: all critical high-word classes and
    # low-word wraps, with representative extreme/interior denominator rows.
    deltas={0,1,2,(1<<41)-2,(1<<41)-1,1<<41}
    for high in (0,1,255,510,511,512):
        for low in (0,1,0x7fffffff,0x80000000,0xfffffffe,0xffffffff):
            v=(high<<32)|low
            if v<=1<<41:
                deltas.add(v)
    rows=[]
    for den in (2049,2051,3071,3073,4093,4095):
        for delta in sorted(deltas|{den-1,den,den+1}):
            exact=(delta<<29)//den
            for state_name,state in states.items():
                outputs={};counts={}
                for label,m in bare.items():
                    m.uc.mem_write(0xd0000060,state)
                    got,_,cost=m.call('mk61_m0_log_ratio70_slow',delta,den,count=True)
                    assert got==exact,(label,den,delta,got,exact)
                    assert bytes(m.uc.mem_read(0xd0000060,28))==state
                    outputs[label]=str(got);counts[label]=cost
                rows.append(dict(den=den,delta=str(delta),SIO=state_name,exact_floor=str(exact),outputs=outputs,instructions=counts))
    assert not sio
    assert max(SP-m.stack_lowest for m in bare.values())<=68
    put('BARE-HELPER-ARM.json',dict(status='PASS_EXACT_ENDPOINT_LOWWORD_WRAP_ARM',
        actual_ARM_calls=len(rows)*2,state_rows=len(rows),rows=rows,
        pure_integer_oracle='unbounded integer floor((delta<<29)/den)',
        all513_high_classes_proved_in_static_certificate=True,
        representative_denominators=[2049,2051,3071,3073,4093,4095],
        firmware_or_ROM_mapped=False,only_extra_seed_capsule_bytes=184,
        seed_capsule_sha256=hashlib.sha256(capsule).hexdigest(),
        SIO_accesses=0,all28bytes_preserved_both_states=True,
        PCS_R4_R11_SP_return_bounded_writes_checked_every_call=True,
        all_code_and_data_accesses_in_component_capsule_or_bounded_stack=True,
        observed_stack_bytes={label:SP-m.stack_lowest for label,m in bare.items()}))

    # Actual public entries use exactly the same pinned resident, captured ROM
    # and Qfplib ELF as the accepted parent. No synthetic FP helper substitutes.
    ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
    RES=V/'firmware/mk61s-picocalc-pico-h.elf'
    REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
    assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
    assert sha(RES)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
    assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
    machines={'Qfplib':Machine(REF,True)}
    for label,path in [('parent',W/'control.elf'),('candidate',D/'candidate.elf')]:
        m=Machine(RES,True,bootrom=ROM)
        image=ElfImage(path);image.load(m.uc)
        m.elf.symbols[label+'_ln']=image.symbols['mk61_m0_ln']
        m.trace=[]
        for name in ('mk61_m0_log_ratio70','mk61_m0_log_ratio70_slow','ln_near_interval','ln_refine','mk61_m0_ln_special'):
            at=image.symbols[name]&~1
            def hit(uc,address,size,user,m=m):
                m.trace.append(user)
            m.uc.hook_add(UC_HOOK_CODE,hit,name,begin=at,end=at)
        machines[label]=m
    jobs={}
    def add(raw,group):
        jobs.setdefault(raw,group)
    for raw in (0,1<<63,1,(1<<52)-1,1<<52,0x7ff0000000000000,0xfff0000000000000,
                0x7ff0000000000001,0x7ff8000000001234,0xfff8000000001234,bits(-1.),bits(1.),bits(2.),bits(4.)):
        add(raw,'unaffected_IEEE_or_power_control')
    gains=[0x3fef7fffffffffe6,0x3fef7fffffffffe8,0x3fef7fffffffffea,0x3fef7fffffffffd9,0x3fef7fffffffffdb]
    for raw in gains:
        add(raw,'five_fixed_DIRTY_losses')
    for index in (0,511,1023):
        for off in (0,1,2,(1<<41)-1,1<<41,(1<<41)+1,(1<<42)-2,(1<<42)-1):
            add((0x400<<52)|(index<<42)|off,'general_endpoint_center_both_signs_of_delta')
    for raw in (0x3fef800000000000,0x3ff0400000000000):
        for change in (-1,0,1):
            add(raw+change,'near_dispatch_boundary')
    regs=get(W/'regressions.json')['rows']
    for rr in (regs[0],regs[2],regs[-1]):
        add(int(rr['x'],16),'retained_one_instruction_regression')
    remaining=get(W/'remaining-slower.json')['rows']
    newly_open=[rr for rr in remaining if rr['group']=='general_quotient_low_word_wrap_controls']
    for rr in newly_open[:2]:
        add(int(rr['x'],16),'preexisting_expanded_wrap_speed_deficit')
    author=get(W/'qualification.json');saved={(rr['x'],rr['SIO']):rr for rr in author['rows']}
    oracle=Oracle();public=[];calls=0
    for raw,group in sorted(jobs.items()):
        expected=oracle.reference('ln',raw)
        for state_name,state in states.items():
            outputs={};counts={};correct={};traces={}
            for label,m in machines.items():
                m.uc.mem_write(0xd0000060,state)
                if label!='Qfplib':
                    m.trace=[]
                got,_,cost=m.call('qfp_dln' if label=='Qfplib' else label+'_ln',raw,count=True)
                calls+=1;outputs[label]=f'{got:016X}';counts[label]=cost;correct[label]=equal(got,expected,64)
                if label!='Qfplib':
                    assert correct[label],(label,hex(raw),hex(got),hex(expected))
                    traces[label]=list(m.trace)
                after=bytes(m.uc.mem_read(0xd0000060,28))
                if state_name=='DIRTY':
                    assert after==state
                else:
                    assert not struct.unpack('<7I',after)[6]&2
            assert outputs['candidate']==outputs['parent']
            assert traces['candidate']==traces['parent']
            if state_name=='READY':
                assert counts['candidate']==counts['parent']
            rr=saved.get((f'{raw:016X}',state_name))
            if rr:
                for label in machines:
                    assert outputs[label]==rr['outputs'][label] and counts[label]==rr['instructions'][label]
            if raw in gains and state_name=='DIRTY':
                assert correct['Qfplib'] and (counts['parent'],counts['candidate'],counts['Qfplib'])==(722,718,719)
            if raw==bits(2.) and state_name=='DIRTY':
                assert (counts['parent'],counts['candidate'],counts['Qfplib'])==(613,610,711)
            public.append(dict(x=f'{raw:016X}',group=group,SIO=state_name,expected=f'{expected:016X}',
                outputs=outputs,instructions=counts,correct=correct,dispatch_trace=traces,
                matched_sealed_author_record=rr is not None))
    assert any('mk61_m0_log_ratio70_slow' in rr['dispatch_trace']['candidate'] for rr in public)
    assert any('ln_near_interval' in rr['dispatch_trace']['candidate'] for rr in public)
    put('SELECTED-PUBLIC-ARM.json',dict(status='PASS_SELECTED_PUBLIC_ENDPOINT_AND_DISPATCH_MPFR',
        unique_inputs=len(jobs),state_rows=len(public),actual_ARM_calls=calls,MPFR_version=oracle.version,
        rows=public,candidate_wrong=0,parent_candidate_raw_policy_equal=True,
        parent_candidate_dispatch_equal=True,all_selected_READY_counts_equal=True,
        five_fixed_DIRTY_counts=[722,718,719],ln2_DIRTY_counts=[613,610,711],
        DIRTY_all28_SIO_bytes_preserved=True,READY_no_DIRTY_left=True,
        PCS_R4_R11_SP_return_and_bounded_writes_checked_every_call=True,
        public_stack_bytes_subset={label:SP-m.stack_lowest for label,m in machines.items()},
        unchanged_near_or_full_ratio_proofs_not_replayed=True,
        no_full_author_corpus_replay=True,hardware_accessed=False,physical_cycles_measured=False))
    print('PASS actual ARM bare',len(rows)*2,'public',calls,'MPFR',oracle.version,'inputs',len(jobs))


if __name__=='__main__':
    main()
