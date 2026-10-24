"""Bounded actual ARM integer-helper and public MPFR controls, no hardware."""
from pathlib import Path
from fractions import Fraction as F
from collections import Counter
import hashlib,json,random,struct,sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[1]
W=ROOT/'.build/m0-log-ratio-dirty-20261024'
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
SUP=ROOT/'.build/m0-float-fma-qualification-20261023/support'
sys.path[:0]=[str(SUP),str(SUP.parent),str(ROOT/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def get(p):return json.loads(Path(p).read_text())
def put(name,value):
    with (OUT/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')
assert sha(OUT/'candidate.elf')=='4e1a6b9151b96b5f9355e75c891c508809cad22d6c67fb9ef33354485acd5dff'
states={'READY':struct.pack('<7I',0,0,0,0,0,0,1),'DIRTY':struct.pack('<7I',17,3,17,3,5,2,3)}
S=1<<46;D=1<<41
def seed_model(delta,R):
    a0=delta&65535;a1=(delta>>16)&65535;b0=R&65535;b1=(R>>16)&65535
    omitted=a0*b0+((a0*b1+a1*b0)<<16)
    return ((delta*R-omitted+(1<<45))>>46)+4

# Bare helper: the reviewed ELF and only its source-bound184-byte capsule.
bare=Machine(OUT/'candidate.elf',True,stack_bytes=128)
capsule=ElfImage(OUT/'seed-kernel.o').bytes_at(ElfImage(OUT/'seed-kernel.o').named_sections['.text.seed'])
seed_address=bare.elf.symbols['mk61_m0_log_product46']&~1
bare.uc.mem_write(seed_address,capsule)
bare.elf.symbols['seed_probe']=seed_address|1
accesses=[]
def sio(uc,access,address,size,value,user):accesses.append((access,address,size))
bare.uc.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,sio,begin=0xd0000060,end=0xd000007b)
table_name=next(n for n in bare.elf.symbols if 'log10_table' in n)
table_address=bare.elf.symbols[table_name]
jobs=[];rng=random.Random(0x1A2D17)
for index in (0,1,255,511,767,796,994,1022,1023):
    den=2049+2*index
    row=struct.unpack('<4I',bare.uc.mem_read(table_address+index*16,16))
    R=(row[1]<<32)|(row[0]&~63)
    assert R==((1<<75)//den)&~63
    values={0,1,(1<<16)-1,1<<16,(1<<16)+1,(1<<32)-1,1<<32,(1<<32)+1,D-2,D-1,D}
    # Choose two opposing seed-error extremes using independent retained-limb
    # integer semantics; this is not a repeat of the author's random ARM set.
    candidates=[rng.randrange(D+1) for _ in range(256)]
    candidates+=list(values)
    key=lambda d:seed_model(d,R)*den-(d<<29)
    values.update((min(candidates,key=key),max(candidates,key=key)))
    jobs += [(den,R,delta) for delta in sorted(values)]
rows=[];corrections=Counter();helper_calls=0
for den,R,delta in jobs:
    exact=(delta<<29)//den
    for state_name,state in states.items():
        bare.uc.mem_write(0xd0000060,state)
        before=len(accesses)
        seed,_,seed_cost=bare.call('seed_probe',delta,R,count=True)
        value,_,cost=bare.call('mk61_m0_log_ratio70_slow',delta,den,count=True)
        assert len(accesses)==before
        assert seed==seed_model(delta,R) and value==exact
        assert F(-106497,16384)<F(seed)-F(delta<<29,den)<=F(9,2)
        assert bytes(bare.uc.mem_read(0xd0000060,28))==state
        corrections[value-seed]+=1;helper_calls+=2
        rows.append(dict(den=den,delta=str(delta),SIO=state_name,seed=str(seed),exact=str(value),correction=value-seed,instructions=cost,seed_instructions=seed_cost))
assert set(corrections)&set(range(-7,0)) and set(corrections)&set(range(1,8))
helper_stack=SP-bare.stack_lowest
assert helper_stack<=68
put('SELECTED-HELPER-ARM.json',dict(status='PASS_BOUNDED_BARE_INTEGER_HELPER_AND_SEED',
 pairs=len(jobs),actual_ARM_calls=helper_calls,denominators=9,rows=rows,
 exact_floor_every_result=True,exact_source_retained_limb_seed_model=True,
 SIO_accesses=0,PCS_SP_bounded_stack_checked_every_call=True,
 stack_bytes_observed=helper_stack,correction_counts=dict(sorted(corrections.items())),
 firmware_or_ROM_loaded=False,additional_seed_bytes=184))

# Actual dispatch entry: inherited ready path and new busy zero/nonzero tail.
dispatch=[]
for den in (2049,4095):
    for delta in (0,1,D-1,D):
        for state_name,state in states.items():
            bare.uc.mem_write(0xd0000060,state)
            accesses.clear()
            got,_,cost=bare.call('mk61_m0_log_ratio70',delta,den,count=True)
            assert got==(delta<<29)//den
            if state_name=='DIRTY':
                assert bytes(bare.uc.mem_read(0xd0000060,28))==state
                assert len(accesses)==1 and accesses[0][1:]==(0xd0000078,4)
            else:
                assert struct.unpack('<7I',bare.uc.mem_read(0xd0000060,28))[6]&2==0
            dispatch.append(dict(den=den,delta=str(delta),SIO=state_name,exact=str(got),instructions=cost,SIO_accesses=len(accesses)))
put('SELECTED-DISPATCH-ARM.json',dict(status='PASS_ACTUAL_READY_DIRTY_DISPATCH_AND_ZERO_ENDPOINTS',
 actual_ARM_calls=len(dispatch),rows=dispatch,DIRTY_only_one_CSR_read_no_writes=True,
 instruction_counts_are_not_cycles=True))

ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
machines={'Qfplib':Machine(REF,True)}
for label,path in (('parent',W/'control.elf'),('candidate',OUT/'candidate.elf')):
    m=Machine(ELF,True,bootrom=ROM)
    image=ElfImage(path);image.load(m.uc)
    m.elf.symbols[label+'_ln']=image.symbols['mk61_m0_ln'];machines[label]=m
historical={int(r['x'],16) for r in get(P/'slower-inputs.json')['rows'] if r['operation']=='ln'}
public=set(historical)
public.update((0,1<<63,1,(1<<52)-1,1<<52,(1<<52)+1,
    0x7fefffffffffffff,0x7ff0000000000000,0xfff0000000000000,
    0x7ff0000000000001,0x7ff8000000001234,0xfff8000000004321,
    bits(0.5),bits(1.0)-1,bits(1.0),bits(1.0)+1,bits(2.0),bits(4.0),bits(-2.0)))
for index in (0,1,255,511,796,994,1022,1023):
    center=0x3ff0000000000000+((2*index+1)<<41)
    public.update((center-1,center,center+1))
oracle=Oracle();rows=[];calls=0
auth={(r['x'],r['SIO']):r for r in get(W/'qualification.json')['rows']}
for raw in sorted(public):
    expected=oracle.reference('ln',raw)
    for state_name,state in states.items():
        outputs={};costs={};correct={}
        for label,m in machines.items():
            m.uc.mem_write(0xd0000060,state)
            symbol='qfp_dln' if label=='Qfplib' else label+'_ln'
            got,_,cost=m.call(symbol,raw,count=True);calls+=1
            outputs[label]=f'{got:016X}';costs[label]=cost;correct[label]=equal(got,expected,64)
            if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
            after=bytes(m.uc.mem_read(0xd0000060,28))
            if state_name=='DIRTY':assert after==state
            else:assert not struct.unpack('<7I',after)[6]&2
        assert outputs['candidate']==outputs['parent']
        assert costs['candidate']<=costs['parent']
        if state_name=='READY':assert costs['candidate']==costs['parent']
        old=auth.get((f'{raw:016X}',state_name))
        if old:
            for label in machines:
                assert outputs[label]==old['outputs'][label] and costs[label]==old['instructions'][label]
        rows.append(dict(x=f'{raw:016X}',SIO=state_name,expected=f'{expected:016X}',outputs=outputs,instructions=costs,correct=correct,existing_record_matched=old is not None))
ln2=next(r for r in rows if r['x']=='4000000000000000' and r['SIO']=='DIRTY')
assert ln2['instructions']=={'Qfplib':711,'parent':1250,'candidate':612}
put('SELECTED-PUBLIC-ARM.json',dict(status='PASS_FRESH_MPFR_BOUNDED_ACTUAL_PUBLIC_LN',
 unique_inputs=len(public),state_rows=len(rows),actual_ARM_calls=calls,rows=rows,
 MPFR_version=oracle.version,full_raw_parent_candidate_NaN_policy_equal=True,
 candidate_stack_bytes_observed=SP-machines['candidate'].stack_lowest,
 parent_stack_bytes_observed=SP-machines['parent'].stack_lowest,
 ABI_SP_return_bounded_writes_checked_every_call=True,
 DIRTY_all28_caller_SIO_bytes_preserved_every_call=True,READY_no_DIRTY_bit_left=True,
 ln2_DIRTY=ln2,author_corpus_not_repeated=True,hardware_accessed=False,
 ROM_sha256=sha(ROM),resident_ELF_sha256=sha(ELF),Qfplib_ELF_sha256=sha(REF)))
print(json.dumps(dict(status='PASS_BOUNDED_ARM_AND_FRESH_MPFR',helper_ARM_calls=helper_calls,dispatch_ARM_calls=len(dispatch),public_ARM_calls=calls,unique_public=len(public),MPFR=oracle.version)))
