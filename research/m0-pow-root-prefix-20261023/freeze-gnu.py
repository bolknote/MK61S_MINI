"""Freeze the experimental schedule with GNU as and compare the full loaded image."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
import hashlib
import ast
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess

root=Path.cwd()
work=Path(_checkpoint_args.work).resolve()
record=json.loads((work/'build.json').read_text())
flags=record['kernel_command']
raw=work/'kernels-clang.s'
subprocess.run(flags+['-S',str(work/'kernels.cpp'),'-o',str(raw)],cwd=root,check=True)
text=raw.read_text()
lines=[]
forced=0
for line in text.splitlines(True):
    if line.lstrip().startswith(('.addrsig','.addrsig_sym')):continue
    match=re.match(r'^\s*(adds|subs)\s+r([0-7]),\s*r([0-7]),\s*#([0-7])\s*(?:@.*)?$',line)
    if match:
        op,rd,rn,imm=match.groups()
        word=(0x1C00 if op=='adds' else 0x1E00)+(int(imm)<<6)+(int(rn)<<3)+int(rd)
        line='\t.inst.n\t'+hex(word)+' @ '+line.strip()+'\n'
        forced+=1
    lines.append(line)
clean=''.join(lines)
clean=re.sub(r'(?<![A-Za-z0-9_])\.L([A-Za-z0-9_.$]+)',r'.Lpow_root_prefix_\1',clean)
assembly=work/'kernels-gnu.S'
assembly.write_text(clean)
compiler=Path(record['source_command'][0]).with_name('arm-none-eabi-gcc')
obj=work/'kernels-gnu.o'
subprocess.run([str(compiler),'-mcpu=cortex-m0plus','-mthumb','-c',str(assembly),'-o',str(obj)],check=True)
link=list(record['link_command'])
link[link.index(str(work/'kernels.o'))]=str(obj)
elf=work/'diagnostic-gnu.elf';link[link.index('-o')+1]=str(elf)
for i,a in enumerate(link):
    if a.startswith('-Wl,-Map='):link[i]='-Wl,-Map='+str(work/'diagnostic-gnu.map')
with (work/'gnu-link.log').open('w') as log:
    subprocess.run(link,cwd=root/'.build/m0-pow-final-parent-v110-20261023/build',stdout=log,stderr=subprocess.STDOUT,check=True)


def loads(path):
    data=path.read_bytes();offset=struct.unpack_from('<I',data,28)[0]
    size,count=struct.unpack_from('<HH',data,42)
    result=[]
    for i in range(count):
        typ,pos,va,pa,filesz,memsz,flags,align=struct.unpack_from('<8I',data,offset+i*size)
        if typ==1:result.append(dict(virtual_address=va,physical_address=pa,file_size=filesz,
            memory_size=memsz,flags=flags,alignment=align,sha256=hashlib.sha256(data[pos:pos+filesz]).hexdigest()))
    return result


before,after=loads(work/'diagnostic.elf'),loads(elf)
assert [{k:v for k,v in x.items() if k!='sha256'} for x in before]==[{k:v for k,v in x.items() if k!='sha256'} for x in after]
import sys
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
namespace=dict(ElfImage=ElfImage,struct=struct)
for node in ast.parse((root/'.build/m0-pow-stable-v87-20261022/link-equivalence.py').read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in ('symbols','object_payload','payload','target'):
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),namespace)
left,right=namespace['object_payload'](work/'kernels.o'),namespace['object_payload'](obj)
empty_gnu_sections=sorted(n for n,v in right['allocated'].items() if not v and n not in left['allocated'])
left['allocated']={n:v for n,v in left['allocated'].items() if v}
right['allocated']={n:v for n,v in right['allocated'].items() if v}
assert left==right,'Allocated object bytes or named relocations differ'
a,b=ElfImage(work/'diagnostic.elf'),ElfImage(elf)
veneer_moves=[]
for name,address in a.symbols.items():
    if name.endswith('_veneer') and b.symbols.get(name)!=address:
        size=a.sizes[name];other=b.symbols[name]
        assert b.sizes[name]==size and namespace['payload'](a,address&~1,size)==namespace['payload'](b,other&~1,size)
        veneer_moves.append(dict(name=name,before=address&~1,after=other&~1,bytes=size))
old_veneers={r['before']:r for r in veneer_moves}
new_veneers={r['after']:r for r in veneer_moves}
changed_calls=[]
for name,section in a.named_sections.items():
    if not section[2]&2 or section[1]==8 or not section[5]:continue
    other=b.named_sections[name]
    assert section[3]==other[3] and section[5]==other[5]
    x,y=a.bytes_at(section),b.bytes_at(other)
    if x==y:continue
    normalized=bytearray(y)
    for row in veneer_moves:
        if section[3]<=row['before']<section[3]+section[5]:
            start=row['before']-section[3]
            normalized[start:start+row['bytes']]=x[start:start+row['bytes']]
    for at in range(0,len(x)-3,2):
        if x[at:at+4]==normalized[at:at+4]:continue
        first=namespace['target'](x[at:at+4],section[3]+at)
        second=namespace['target'](y[at:at+4],section[3]+at)
        if first in old_veneers and second in new_veneers and old_veneers[first]['name']==new_veneers[second]['name']:
            normalized[at:at+4]=x[at:at+4]
            changed_calls.append(dict(section=name,offset=at,target=old_veneers[first]['name']))
    assert bytes(normalized)==x,(name,'Difference is not a proven equivalent veneer relocation')
(work/'gnu-equivalence.json').write_text(json.dumps(dict(status='PASS_GNU_KERNEL_BYTES_AND_NAMED_CALL_EQUIVALENCE',
    clang_elf_sha256=hashlib.sha256((work/'diagnostic.elf').read_bytes()).hexdigest(),
    gnu_elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),
    cpp_sha256=hashlib.sha256((work/'kernels.cpp').read_bytes()).hexdigest(),
    assembly_sha256=hashlib.sha256(assembly.read_bytes()).hexdigest(),segments=after,
    full_loaded_image_byte_identical=before==after,forced_imm3_encodings=forced,
    local_labels_renamed_to_avoid_existing_assembly_collisions=True,
    empty_GNU_sections_ignored=empty_gnu_sections,object_allocations_and_named_relocations_identical=True,
    permuted_identical_veneers=veneer_moves,equivalent_calls=changed_calls,
    producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    scope='Every nonempty allocated kernel section and named relocation is identical. All linked differences are calls to two permuted veneers with identical bodies and targets; loaded addresses/sizes/permissions remain equal. Literal byte identity of the whole linked image is not claimed. Physical cache behavior still requires a separate check. No firmware installation or production promotion.'),indent=2)+'\n')
print('PASS: exact GNU kernel allocations/relocations;',len(changed_calls),'equivalent calls;',len(veneer_moves),'permuted veneers.')
