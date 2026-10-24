"""Build private exp and a shorter RAM product with frozen release flags."""
from pathlib import Path
import hashlib
import json
import shlex
import subprocess
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
db=P/'build/compile_commands.json'
entry=next(d for d in json.loads(db.read_text()) if d['file'].endswith('/code/native_eabi_m0.cpp'))
original=shlex.split(entry['command'])
assert '-fno-lto' in original and '-Os' in original
cc=Path(original[0]).parent
release_object=Path(entry['output'])
assert release_object.exists()
commands=[]
for label in ('control','candidate'):
    command=list(original)
    command[command.index(entry['file'])]=str(W/label/'native_eabi_m0.cpp')
    command[command.index('-o')+1]=str(W/(label+'-full.o'))
    subprocess.run(command,cwd=W,check=True);commands.append(command)

def allocated(im):return {n:im.bytes_at(s) for n,s in im.named_sections.items() if s[2]&2 and s[1]!=8}
original_object=ElfImage(release_object)
control=ElfImage(W/'control-full.o')
assert allocated(original_object)==allocated(control),'Control differs from frozen release allocated bytes'
old,new=allocated(control),allocated(ElfImage(W/'candidate-full.o'))
assert set(old)==set(new)
changed={n:[len(old[n]),len(new[n])] for n in old if old[n]!=new[n]}
assert set(changed)=={'.m0_exp_core'},changed
trial=ElfImage(ROOT/'.build/m0-exp-tight-firstpass-20261024/candidate-full.o')
assert allocated(trial)==new,'Only the RAM product may differ from the tight CPP trial'
command=[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb',
    '-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-c',str(W/'cached-product.S'),
    '-o',str(W/'cached-product.o')]
subprocess.run(command,cwd=W,check=True);commands.append(command)

text=(W/'bindings.ld').read_text()
bindings={}
for line in text.splitlines():
    if '= 0x' in line and line.strip().split(' = ')[0]!='.':
        name,value=line.split(' = ');bindings[name]=int(value.strip(';'),16)
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
for name,address in bindings.items():
    expected=resident.symbols['__wrap_'+name] if name in ('memcpy','memset') else resident.symbols[name]
    assert address==expected,(name,address,expected)
for label in ('control','candidate'):
    script=W/('candidate-bindings.ld' if label=='candidate' else 'bindings.ld')
    objects=[str(W/(label+'-full.o'))]+([str(W/'cached-product.o')] if label=='candidate' else [])
    command=[str(cc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_exp','-T',str(script),*objects,'-o',str(W/(label+'.elf'))]
    subprocess.run(command,check=True);commands.append(command)
    im=ElfImage(W/(label+'.elf'))
    flash_ranges=[(s[3],s[3]+s[5]) for n,s in im.named_sections.items() if s[2]&2 and s[5] and n!='.product_ram']
    assert all(0x101a0000<=a<z<=0x10200000 for a,z in flash_ranges)
    assert all(not any(a<=(v&~1)<z for a,z in flash_ranges) for v in bindings.values())
    for name,address in bindings.items():
        assert im.symbols[name]==address,(label,name)
    if label=='candidate':
        product=im.named_sections['.product_ram']
        assert product[3]==resident.symbols['mk61_m0_pow_exp_product']&~1
        assert product[5]==resident.sizes['mk61_m0_pow_exp_product']-14
        assert not product[2]&1,'Product overlay must not be writable'
        assert product[5]==im.sizes['mk61_m0_pow_exp_product']
    assert not subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/(label+'.elf'))],text=True)
    with (W/(label+'.dis')).open('w') as f:
        subprocess.run([str(cc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)

out=dict(status='BUILT_PRIVATE_EXP_CACHED_RAM_PRODUCT_AND_TINY_RNE',commands=commands,
    source_sha256=sha(W/'candidate/native_eabi_m0.cpp'),control_source_sha256=sha(W/'control/native_eabi_m0.cpp'),
    parent_source_sha256=sha(P/'source/code/native_eabi_m0.cpp'),candidate_ELF_sha256=sha(W/'candidate.elf'),
    control_ELF_sha256=sha(W/'control.elf'),candidate_object_sha256=sha(W/'candidate-full.o'),
    control_object_sha256=sha(W/'control-full.o'),original_release_object_sha256=sha(release_object),
    all_control_allocated_sections_byte_exact_release=True,changed_object_sections=changed,
    allocated_object_bytes_delta=sum(map(len,new.values()))-sum(map(len,old.values())),
    product_source_sha256=sha(W/'cached-product.S'),product_object_sha256=sha(W/'cached-product.o'),
    product_body_bytes_delta=-14,product_instruction_delta=-7,
    product_RAM_address=hex(resident.symbols['mk61_m0_pow_exp_product']&~1),
    product_stack_bytes=40,parent_product_stack_bytes=32,
    CPP_allocated_bytes_identical_tight_trial=True,Flash_wrapper_unchanged=True,
    original_compile_database_sha256=sha(db),resident_bindings=bindings,hardware_accessed=False,
    canonical_Git_or_frozen_changed=False,compiler_flags_preserved=True)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('commands','resident_bindings')},indent=2))
