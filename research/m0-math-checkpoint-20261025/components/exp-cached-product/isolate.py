"""Verify exp CPP/product scope and byte-identical generic M0/M4 controls."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
build=json.loads((W/'build.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def allocated(im):return {n:im.bytes_at(s) for n,s in im.named_sections.items() if s[2]&2 and s[1]!=8}
old,new=ElfImage(W/'control-full.o'),ElfImage(W/'candidate-full.o')
a,b=allocated(old),allocated(new)
assert set(a)==set(b)
assert {n for n in a if a[n]!=b[n]}=={'.m0_exp_core'}
def body(im,name):
    address=im.symbols[name]&~1;size=im.sizes[name]
    s=im.named_sections['.m0_exp_core']
    return im.bytes_at(s)[address-s[3]:address-s[3]+size]
assert body(old,'exp_refine')==body(new,'exp_refine')
commands=[];contexts=[]
for context,cpu,enabled,hard in (('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)):
    images=[]
    for index,label in enumerate(('control','candidate')):
        command=[v for v in build['commands'][index] if v!='-DMK61_M0_RP2040_EABI=1']
        command[command.index('-mcpu=cortex-m0plus')]='-mcpu='+cpu
        if not enabled:
            command[command.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
        if hard:command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
        output=W/(context+'-'+label+'.o');command[command.index('-o')+1]=str(output)
        subprocess.run(command,cwd=W,check=True);commands.append(command);images.append(ElfImage(output))
    assert allocated(images[0])==allocated(images[1]),context
    contexts.append(dict(context=context,allocated_code_and_data_identical=True,allocated_bytes=sum(map(len,allocated(images[1]).values()))))
cc=Path(build['commands'][0][0]).parent
undefined=lambda n:sorted(subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(W/n)],text=True).splitlines())
assert undefined('control-full.o')==undefined('candidate-full.o')
control,candidate=ElfImage(W/'control.elf'),ElfImage(W/'candidate.elf')
data=lambda im:{n:im.bytes_at(s) for n,s in im.named_sections.items() if s[2]&2 and not s[2]&4 and s[1]!=8}
assert data(control)==data(candidate)
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
product_name='mk61_m0_pow_exp_product'
address=resident.symbols[product_name]&~1
section=next(s for s in resident.named_sections.values() if s[3]<=address<s[3]+s[5])
old_product=resident.bytes_at(section)[address-section[3]:address-section[3]+resident.sizes[product_name]]
command=[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb',
    '-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-x','assembler-with-cpp',
    '-c',str(P/'source/code/native_eabi_m0_pow_exp_product.inc'),'-o',str(W/'control-product.o')]
subprocess.run(command,check=True);commands.append(command)
old_object=ElfImage(W/'control-product.o')
old_section=old_object.named_sections['.scratch_y.m0_pow_hot']
old_bytes=old_object.bytes_at(old_section)
old_start=(old_object.symbols[product_name]&~1)-old_section[3]
assert old_object.sizes[product_name]==len(old_product)
assert old_bytes[old_start:old_start+len(old_product)]==old_product
product_object=ElfImage(W/'cached-product.o')
new_product=product_object.bytes_at(product_object.named_sections['.scratch_y.m0_exp_product_only'])
assert new_product==candidate.bytes_at(candidate.named_sections['.product_ram'])
assert len(new_product)==len(old_product)-14
assert candidate.symbols[product_name]==resident.symbols[product_name]
assembly_contexts=[]
for context,cpu in (('generic_M0','cortex-m0plus'),('M4_soft','cortex-m4'),('M4_hard','cortex-m4')):
    command=[str(cc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-DMK61_USE_M0_EABI=1',
        '-c',str(W/'cached-product.S'),'-o',str(W/(context+'-product.o'))]
    if context=='M4_hard':command+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
    subprocess.run(command,check=True);commands.append(command)
    image=ElfImage(W/(context+'-product.o'))
    assert sum(map(len,allocated(image).values()))==0
    assembly_contexts.append(dict(context=context,excluded_product_allocated_bytes=0))
out=dict(status='PASS_RP_EXP_ENTRY_AND_SHORTER_RAM_PRODUCT_GENERIC_M0_M4_IDENTICAL',
    source_sha256=build['source_sha256'],candidate_ELF_sha256=build['candidate_ELF_sha256'],
    only_changed_CPP_object_section='.m0_exp_core',exp_refine_body_byte_identical=True,
    all_other_CPP_allocated_code_tables_BSS_and_dependencies_identical=True,new_tables_global_RAM_or_libgcc=False,
    allocated_object_bytes_delta=build['allocated_object_bytes_delta'],contexts=contexts,commands=commands,
    assembly_contexts=assembly_contexts,product_bytes=[len(old_product),len(new_product)],
    product_body_bytes_delta=-14,total_CPP_and_product_body_bytes_delta=30,
    product_object_section_bytes=[len(old_bytes),len(new_product)],
    product_object_section_allocated_bytes_delta=len(new_product)-len(old_bytes),
    total_CPP_and_product_object_allocated_bytes_delta=build['allocated_object_bytes_delta']+len(new_product)-len(old_bytes),
    whole_firmware_linked_size_delta_not_measured=True,
    product_RAM_address_unchanged=True,Flash_wrapper_unchanged=True,
    original_product_reassembles_byte_exact_resident=True,
    cached_product_object_bytes_exact_candidate_ELF=True,
    scope='Same frozen release flags and selected translation-unit controls; no whole M4 firmware or hardware qualification.',hardware_accessed=False)
(W/'isolation.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
