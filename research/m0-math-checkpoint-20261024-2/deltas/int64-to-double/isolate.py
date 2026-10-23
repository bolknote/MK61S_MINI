"""Audit public-object equivalence and unaffected M4/generic M0 contexts."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
commands=[]
def compile(source,output,cpu='cortex-m0plus',rp=True,use=True,hard=False):
    command=[str(CC/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),'-I',str(P)]
    if rp:command+=['-DMK61_M0_RP2040_EABI=1']
    if use:command+=['-DMK61_USE_M0_EABI=1']
    if hard:command+=['-mfpu=fpv4-sp-d16']
    command+=['-c',str(source),'-o',str(output)]
    subprocess.run(command,check=True);commands.append(command);return ElfImage(output)
def allocated(image):return {n:image.bytes_at(s) for n,s in image.named_sections.items() if s[2]&2 and s[1]!=8}
def undefined(path):return sorted(subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(path)],text=True).splitlines())
old=compile(P/'native_eabi_m0.S',W/'control-full.o')
new=compile(W/'native_eabi_m0.S',W/'candidate-full.o')
a,b=allocated(old),allocated(new);assert set(a)==set(b)
changed=[n for n in a if a[n]!=b[n]]
assert changed==['.text.__aeabi_i2d'],changed
diagnostic=ElfImage(W/'candidate.elf')
assert b['.text.__aeabi_i2d']==diagnostic.bytes_at(diagnostic.named_sections['.text'])
for name in ('__aeabi_i2d','__aeabi_ui2d','__aeabi_l2d','__aeabi_ul2d'):
    assert new.symbols[name]==diagnostic.symbols[name]-0x10185000,name
assert undefined(W/'candidate-full.o')==undefined(W/'control-full.o')
assert not undefined(W/'candidate.o')
assert not any(s[1] in (4,9) and s[5] for s in diagnostic.sections)
contexts=[]
for label,cpu,use,hard in [('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)]:
    before=compile(P/'native_eabi_m0.S',W/(label+'-control.o'),cpu,False,use,hard)
    after=compile(W/'native_eabi_m0.S',W/(label+'-candidate.o'),cpu,False,use,hard)
    assert allocated(before)==allocated(after),label
    contexts.append(dict(context=label,allocated_code_and_data_identical=True,allocated_bytes=sum(map(len,allocated(after).values()))))
report=dict(status='PASS_RP2040_SIGNED64_ENTRY_ONLY_NO_NEW_DEPENDENCY',changed_allocated_sections=changed,
            old_i2d_section_bytes=len(a[changed[0]]),candidate_i2d_section_bytes=len(b[changed[0]]),
            code_bytes_delta=len(b[changed[0]])-len(a[changed[0]]),
            all_other_allocated_sections_identical=True,public_section_equals_executed_diagnostic_without_exclusions=True,
            all_four_public_entry_offsets_match=True,undefined_dependencies_unchanged=True,
            standalone_undefined_symbols=[],standalone_relocations=[],contexts=contexts,
            source_sha256=sha(W/'native_eabi_m0_convert.inc'),candidate_full_object_sha256=sha(W/'candidate-full.o'),
            candidate_ELF_sha256=sha(W/'candidate.elf'),producer_sha256=sha(Path(__file__)),commands=commands,
            scope='Compile-object isolation; no new production link or whole M4 firmware rebuild.',
            new_tables_or_global_RAM=False,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'isolation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
