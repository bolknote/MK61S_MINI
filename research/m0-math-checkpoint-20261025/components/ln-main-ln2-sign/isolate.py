"""Check that only RP ln packing/dispatch changes, with all helpers retained."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
ROOT = W.parents[1]
BASE = ROOT/'.build/m0-ln-near-q77-linear-20261024'
P = ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
CC = Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def allocated(image):
    return {n:image.bytes_at(s) for n,s in image.named_sections.items() if s[2]&2 and s[1]!=8}


old,new = ElfImage(W/'control-full.o'),ElfImage(W/'candidate-full.o')
a,b = allocated(old),allocated(new)
assert set(a)==set(b)
changed = [n for n in a if a[n]!=b[n]]
assert set(changed)=={'.text.ln_main_raw','.text.mk61_m0_ln_positive'},changed


def function_bytes(image,name,section_name):
    s=image.named_sections[section_name]
    address,size=image.symbols[name]&~1,image.sizes[name]
    return image.bytes_at(s)[address-s[3]:address-s[3]+size]


assert function_bytes(old,'mk61_m0_log10_special','.m0_log_subnormal')==function_bytes(new,'mk61_m0_log10_special','.m0_log_subnormal')
assert sha(W/'native_eabi_m0_log_subnormal.inc')==sha(BASE/'native_eabi_m0_log_subnormal.inc')
assert sha(W/'candidate-ratio.o')==sha(W/'control-ratio.o')==sha(BASE/'candidate-ratio.o')
undefined=lambda p:sorted(subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(p)],text=True).splitlines())
assert undefined(W/'control-full.o')==undefined(W/'candidate-full.o')
contexts=[];commands=[]
for label,cpu,enabled,hard in [('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)]:
    images=[]
    for variant,source in [('control',BASE/'native_eabi_m0.cpp'),('candidate',W/'native_eabi_m0.cpp')]:
        cmd=[str(CC/'arm-none-eabi-g++'),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),
             '-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-use-cxa-atexit',
             '-ffunction-sections','-fdata-sections','-fno-lto','-I',str(P/'source/code')]
        if enabled:cmd+=['-DMK61_USE_M0_EABI=1']
        if hard:cmd+=['-mfpu=fpv4-sp-d16']
        out=W/(label+'-'+variant+'.o');cmd+=['-c',str(source),'-o',str(out)]
        subprocess.run(cmd,check=True);commands.append(cmd);images.append(ElfImage(out))
    assert allocated(images[0])==allocated(images[1]),label
    contexts.append(dict(context=label,allocated_code_and_data_identical=True,allocated_bytes=sum(map(len,allocated(images[1]).values()))))
parent=ElfImage(W/'control.elf');candidate=ElfImage(W/'candidate.elf')
assert parent.bytes_at(parent.named_sections['.rodata'])==candidate.bytes_at(candidate.named_sections['.rodata'])
out=dict(status='PASS_ONLY_RP_MAIN_LN_TWO_UPPER_GUARDS_CHANGED',
    changed_sections={n:[len(a[n]),len(b[n])] for n in changed},
    allocated_object_bytes_delta=sum(map(len,b.values()))-sum(map(len,a.values())),
    all_other_allocated_sections_tables_and_dependencies_identical=True,
    log10_special_byte_identical=True,ratio_ASM_object_byte_identical=True,
    no_new_tables_global_RAM_or_libgcc=True,
    inherited_near_Q77_function_and_tables_byte_identical=True,contexts=contexts,commands=commands,
    source_sha256=sha(W/'native_eabi_m0_log70.inc'),subnormal_source_sha256=sha(W/'native_eabi_m0_log_subnormal.inc'),
    candidate_ELF_sha256=sha(W/'candidate.elf'),full_object_sha256=sha(W/'candidate-full.o'),
    hardware_accessed=False,canonical_or_frozen_changed=False,
    scope='Private ln component and compile controls; no whole M4 or production firmware rebuild.')
(W/'isolation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
