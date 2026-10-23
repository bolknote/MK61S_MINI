"""Targeted ARM comparison for the changed mixed-sign add/sub branch only."""
from pathlib import Path
import collections,gzip,hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from oracles import integer_binary,equal
ELF=P/'firmware/mk61s-picocalc-pico-h.elf'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
m=Machine(ELF,True,stack_bytes=4096,bootrom=ROM)
reference=Machine(REF,True,stack_bytes=4096)
candidate=ElfImage(W/'candidate.elf')
m.uc.mem_write(0x10180000,(W/'candidate.bin').read_bytes())
for name in ('candidate_dadd','candidate_dsub'):m.elf.symbols[name]=candidate.symbols[name]
oracle=Oracle();start=time.monotonic()
known=[r for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation'] in ('dadd','dsub')]
jobs=[]
for row in known:jobs.append((row['operation'],int(row['x'],16),int(row['y'],16),'known_slower'))
if '--edges' in sys.argv:
    rng=random.Random(0x614ADDF)
    fractions=[0,1,2,(1<<51)-1,1<<51,(1<<52)-2,(1<<52)-1]
    # All alignment categories, each normal guard boundary and both orders.
    for e in (1,2,54,55,56,1022,1023,1024,2044,2045,2046):
        for gap in (0,1,2,3,20,21,30,31,32,33,51,52,53,54,55,56,63,64):
            if e-gap<1:continue
            for f in fractions:
                a=(e<<52)|f;b=((e-gap)<<52)|rng.choice(fractions)
                for x,y in ((a,b|(1<<63)),(b|(1<<63),a),(a|(1<<63),b),(b,a|(1<<63))):
                    jobs.append(('dadd',x,y,'alignment_and_guard'))
                    jobs.append(('dsub',x,y^(1<<63),'alignment_and_guard'))
    edge=[0,1<<63,1,(1<<52)-1,1<<52,0x3ff0000000000000,0x7fefffffffffffff,
          0x7ff0000000000000,0xfff0000000000000,0x7ff0000000000001,0xfff8000000000001]
    for x in edge:
        for y in edge:
            for op in ('dadd','dsub'):jobs.append((op,x,y,'IEEE_fallback'))
    for _ in range(1024):
        e=rng.randrange(55,2046);gap=rng.randrange(2,min(e,55))
        a=(e<<52)|rng.getrandbits(52);b=((e-gap)<<52)|rng.getrandbits(52)
        if rng.getrandbits(1):a,b=b,a
        if rng.getrandbits(1):a|=1<<63
        else:b|=1<<63
        jobs.append(('dadd',a,b,'mixed_random'))
        jobs.append(('dsub',a,b^(1<<63),'mixed_random'))
jobs=list(dict.fromkeys(jobs))
state=struct.pack('<7I',17,3,17,3,5,2,3)
rows=[];failures=[];summary=collections.defaultdict(collections.Counter)
for op,a,b,group in jobs:
    expected=integer_binary('add' if op=='dadd' else 'sub',a,b,width=64)
    mpfr=oracle.reference(op,a,b)
    assert equal(expected,mpfr,64),('oracle disagreement',op,hex(a),hex(b),hex(expected),hex(mpfr))
    count=(group=='known_slower')
    outputs={};cost={}
    for label,name,machine in (('candidate','candidate_'+op,m),('baseline','__aeabi_'+op,m),('Qfplib','qfp_'+op,reference)):
        machine.uc.mem_write(0xd0000060,state)
        value,_,instructions=machine.call(name,a,b,count=count)
        assert bytes(machine.uc.mem_read(0xd0000060,28))==state
        outputs[label]=f'{value:016X}';cost[label]=instructions if count else None
        correct=equal(value,expected,64)
        summary[group][label+'_wrong']+=not correct
        if label!='Qfplib' and not correct:
            failure=dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',expected=f'{expected:016X}',label=label,got=f'{value:016X}')
            (W/'FAILURE.json').write_text(json.dumps(failure,indent=2)+'\n')
            raise AssertionError(failure)
    summary[group]['cases']+=1
    rows.append(dict(operation=op,x=f'{a:016X}',y=f'{b:016X}',group=group,expected=f'{expected:016X}',outputs=outputs,instructions=cost))
    if len(rows)%512==0:print('progress',len(rows),'/',len(jobs),flush=True)
report=dict(status='PASS_TARGETED_PRIVATE_ARM_CANDIDATE_NOT_FIRMWARE_ACCEPTANCE',
            elapsed_seconds=time.monotonic()-start,cases=len(jobs),ARM_calls=len(jobs)*3,
            groups=dict(summary),rows=rows,MPFR_version=oracle.version,
            input_ELF_sha256=sha(ELF),candidate_ELF_sha256=sha(W/'candidate.elf'),ROM_sha256=sha(ROM),
            PCS_SP_and_bounded_stack_writes_checked_every_call=True,READY_DIRTY_SIO_preserved_every_call=True,
            scope='Finite targeted branch validation, not an all-input speed proof. Instruction counts only on retained known slower inputs; counts are ARM instructions, not hardware cycles.',
            canonical_or_frozen_files_changed=False,USB_accessed=False,goal_complete=False)
name='edges.json' if '--edges' in sys.argv else 'smoke.json'
(W/name).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('rows',)}),flush=True)
