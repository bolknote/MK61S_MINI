"""Inspect the cold dispatcher on zeros, negatives, infinities and NaNs."""
import hashlib,json
from pathlib import Path
import struct,sys
root=Path.cwd();work=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'tests'))
from native_eabi_m0_arm_self_test import Machine,nan
from m0_mpfr_oracle import Oracle,bits
from check_stm32_vectors import ElfImage
before=root/'.build/m0-trig-fullrange-v150-20261023/firmware/mk61s-picocalc-pico-h.elf'
after=work/'firmware/mk61s-picocalc-pico-h.elf';rom=root/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
old,new=[Machine(p,True,stack_bytes=16384,instruction_budget=200000000,bootrom=rom) for p in (before,after)]
ref=ElfImage(root/'.build/m0-v138-execution-20261023/reference/reference.elf');ref.load(new.uc)
new.elf.symbols.update({n:a for n,a in ref.symbols.items() if n.startswith('qfp_')})
config=json.loads((root/'.build/m0-v138-execution-20261023/benchmark.json').read_text())
qnames={r['operation']:r['qfplib_symbol'] for r in config['chunks']}
oracle=Oracle();sign=1<<63;inf=0x7ff0000000000000
inputs=[0,sign,1,sign|1,0xFFFFFFFFFFFFF,sign|0xFFFFFFFFFFFFF,
        bits(1.),bits(-1.),bits(-2.),inf,sign|inf,inf|1,sign|inf|1,
        inf|(1<<51),sign|inf|(1<<51),inf|((1<<52)-1),sign|inf|((1<<52)-1)]
rows=[]
for op in ('ln','log10','sqrt'):
    for x in inputs:
        expected=oracle.reference(op,x);name='_ZN12compact_math'+str(len(op))+op+'Ed'
        a,_,ac=old.call(name,x,count=True);b,_,bc=new.call(name,x,count=True)
        q,_,qc=new.call(qnames[op],x,count=True)
        same=lambda v:(nan(v) and bool(v&(1<<51))) if nan(expected) else v==expected
        assert same(a) and same(b)
        rows.append(dict(operation=op,x=f'{x:016X}',expected=f'{expected:016X}',before=f'{a:016X}',
            after=f'{b:016X}',qfplib=f'{q:016X}',before_instructions=ac,after_instructions=bc,
            qfplib_instructions=qc,qfplib_correct=same(q)))
report=dict(status='PASS_COLD_SPECIAL_CORRECTNESS_PROFILE_NOT_SPEED_PASS',cases=len(rows),rows=rows,
    slower_than_V150=[r for r in rows if r['after_instructions']>r['before_instructions']],
    elf_sha256=hashlib.sha256(after.read_bytes()).hexdigest(),baseline_elf_sha256=hashlib.sha256(before.read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),hardware_accessed=False,goal_complete=False)
(work/'special-profile.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(rows),'RNE-correct cold cases;',len(report['slower_than_V150']),'slower thanV150.')
for r in report['slower_than_V150']:print(r['operation'],r['x'],r['before_instructions'],'->',r['after_instructions'])
