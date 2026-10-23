"""Compile-object audit: only the selected dadd block may differ."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-mixed-sign-top-normal-20261023/native_eabi_m0_rp2040.S'
INCLUDES=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin/arm-none-eabi-gcc')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
commands=[]
def build(src,out,cpu='cortex-m0plus',rp=True,hard=False):
    cmd=[str(CC),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),'-DMK61_USE_M0_EABI=1','-I',str(INCLUDES)]
    if hard:cmd+=['-mfpu=fpv4-sp-d16']
    if rp:cmd+=['-DMK61_M0_RP2040_EABI=1']
    cmd+=['-c',str(src),'-o',str(out)]
    subprocess.run(cmd,check=True);commands.append(cmd);return ElfImage(out)
def allocated(e):
    return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
old=build(P,W/'control-full.o');new=build(W/'native_eabi_m0_rp2040.S',W/'candidate-full.o')
a,b=allocated(old),allocated(new)
assert set(a)==set(b)
changed=[n for n in a if a[n]!=b[n]]
assert changed==['.text.mk61_rp2040_arithmetic'],changed
first=old.symbols['mk61_m0_dadd_end'];second=new.symbols['mk61_m0_dadd_end']
assert a[changed[0]][first:]==b[changed[0]][second:]
contexts=[]
for label,cpu,hard in [('M4_soft','cortex-m4',False),('M4_hard','cortex-m4',True),('generic_M0','cortex-m0plus',False)]:
    before=build(P,W/(label+'-control.o'),cpu,False,hard)
    after=build(W/'native_eabi_m0_rp2040.S',W/(label+'-candidate.o'),cpu,False,hard)
    assert allocated(before)==allocated(after)
    contexts.append(dict(context=label,allocated_code_and_data_identical=True,allocated_bytes=sum(map(len,allocated(after).values()))))
report=dict(status='PASS_COLD_NORMAL_ONLY_DADD_BLOCK_CHANGED',
    changed_allocated_sections=changed,control_dadd_block_bytes=first,candidate_dadd_block_bytes=second,
    block_bytes_delta=second-first,all_other_allocated_sections_identical=True,
    remaining_multiply_divide_kernel_bytes_identical=True,contexts=contexts,
    scope='Compile-object isolation only, not a new linked production image or global M4 rebuild. Canonical and frozen sources remain unchanged.',
    commands=commands,source_sha256=hashlib.sha256((W/'native_eabi_m0_rp2040.S').read_bytes()).hexdigest(),
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    canonical_changed=False,hardware_accessed=False)
(W/'object-isolation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
