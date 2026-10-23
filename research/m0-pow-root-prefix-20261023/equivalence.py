"""Prove layout-only numerical equivalence to the fully tested V121 source."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
import ast
import hashlib
import json
from pathlib import Path
import struct
import sys

root=Path.cwd();work=Path(_checkpoint_args.work).resolve()
parent=root/'.build/m0-pow-root-prefix-v121-20261023'
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
namespace=dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for filename,names in [('.build/m0-memory-compose-v79-20261021/prepare.py',('fingerprint',)),
    ('.build/m0-pow-stable-v87-20261022/link-equivalence.py',('symbols','object_payload','payload','target'))]:
    for node in ast.parse((root/filename).read_text()).body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),namespace)
manifest=load(work/'firmware/manifest.json')
assert namespace['fingerprint'](work/'source')==manifest['source_sha256']
files=lambda tree:{str(p.relative_to(tree)):p for p in tree.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
left,right=files(parent/'source'),files(work/'source')
assert left.keys()==right.keys()
assert [n for n in left if left[n].read_bytes()!=right[n].read_bytes()]==['ports/picocalc/m0_math_extension.ld']
functions=set();data_names=set();objects=[]
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    a=next((parent/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    b=next((work/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    x,y=namespace['object_payload'](a),namespace['object_payload'](b)
    assert x==y,(name,'Numerical allocation/relocation changed')
    objects.append(dict(object=name,payload_sha256=hashlib.sha256(json.dumps(x,sort_keys=True).encode()).hexdigest()))
    for symbol in namespace['symbols'](ElfImage(a)):
        if not symbol['size']:continue
        if symbol['info']&15==2:functions.add(symbol['name'])
        if symbol['info']&15==1:data_names.add(symbol['name'])
old_path=parent/'firmware/mk61s-picocalc-pico-h.elf';new_path=work/'firmware/mk61s-picocalc-pico-h.elf'
old,new=ElfImage(old_path),ElfImage(new_path)
all_symbols=[namespace['symbols'](old),namespace['symbols'](new)]
def at(image_index,address):
    return [s for s in all_symbols[image_index] if s['info']&15==2 and s['size'] and (s['value']&~1)==address]
seen=set();changed=[]
def same_function(name):
    key=name
    if key in seen:return True
    assert name in old.symbols and name in new.symbols,name
    a,b=old.symbols[name]&~1,new.symbols[name]&~1
    size=old.sizes[name]
    assert new.sizes[name]==size,(name,'Function size changed')
    seen.add(key)
    x,y=namespace['payload'](old,a,size),namespace['payload'](new,b,size)
    if x==y:return True
    normalized=bytearray(y);calls=[]
    for offset in range(0,size-3,2):
        if x[offset:offset+4]==normalized[offset:offset+4]:continue
        ta=namespace['target'](x[offset:offset+4],a+offset)
        tb=namespace['target'](y[offset:offset+4],b+offset)
        if ta is None or tb is None:continue
        names={s['name'] for s in at(0,ta)}&{s['name'] for s in at(1,tb)}
        if not names:continue
        target=sorted(names,key=lambda n:('veneer' in n,len(n)))[0]
        assert same_function(target)
        normalized[offset:offset+4]=x[offset:offset+4]
        calls.append(dict(offset=offset,target=target))
    assert bytes(normalized)==x,(name,'Difference is not a BL to an equivalent named function')
    changed.append(dict(function=name,before=hex(a),after=hex(b),calls=calls))
    return True
kept=[];discarded=[];moved=[]
for name in sorted(functions):
    assert (name in old.symbols)==(name in new.symbols),(name,'GC membership changed')
    if name not in old.symbols:discarded.append(name);continue
    assert same_function(name)
    if old.symbols[name]!=new.symbols[name]:
        assert name=='pow_sqrt64_raw' or name.endswith('_veneer'),(name,'Unexpected numerical relocation')
        moved.append(dict(function=name,before=hex(old.symbols[name]&~1),after=hex(new.symbols[name]&~1)))
    kept.append(name)
for name in sorted(data_names):
    if name not in old.symbols:continue
    assert name in new.symbols and old.sizes[name]==new.sizes[name]
    assert old.symbols[name]==new.symbols[name],(name,'Numerical data moved')
    size=old.sizes[name]
    # Zero-initialized objects are equal by section/size and source identity.
    try:
        x=namespace['payload'](old,old.symbols[name],size)
        y=namespace['payload'](new,new.symbols[name],size)
    except AssertionError:continue
    assert x==y,(name,'Numerical data changed')
assert new.symbols['pow_sqrt64_raw']&~1==0x1014DA60
assert new.symbols['pow_sqrt64_coefficients']==old.symbols['pow_sqrt64_coefficients']==0x1016BC60
for name in ('__HeapLimit','__StackBottom','__StackTop','__StackOneBottom','__StackOneTop','__scratch_y_start__','__scratch_y_end__'):
    assert new.symbols[name]==old.symbols[name],name
assert new.named_sections['.scratch_y'][5]==old.named_sections['.scratch_y'][5]==4072
assert manifest['static_ram_bytes']==198856 and manifest['flash_bytes']==1537008
references={}
for name in ('all12.json','affected.json','endpoints.json','certificate.json','validation.json','runtime-memory.json',
             'm4-check/m4-isolation.json','generic-m0-isolation.json'):
    p=parent/name;report=load(p);assert report['status'].startswith('PASS'),name
    if 'elf_sha256' in report:assert report['elf_sha256']==sha(old_path),name
    references[name]=dict(path=str(p.relative_to(root)),sha256=sha(p))
result=dict(status='PASS_LAYOUT_ONLY_NUMERICAL_EQUIVALENCE',build=manifest['build_id'],source_sha256=manifest['source_sha256'],
    parent_elf_sha256=sha(old_path),elf_sha256=sha(new_path),identical_numerical_objects_and_relocations=objects,
    surviving_numeric_functions_checked=len(kept),same_discarded_numeric_functions=discarded,
    relocated_functions=moved,functions_with_only_equivalent_named_calls=changed,
    static_ram_bytes=198856,heap_bytes=30520,scratch_used_bytes=4072,image_extent_bytes=1537008,
    correctness_reports_reused_by_code_equivalence=references,
    original_all12_cases=sum(r['cases'] for r in load(parent/'all12.json')['operations'].values()),
    original_affected_cases=load(parent/'affected.json')['cases'],
    producer_sha256=sha(__file__),hardware_ready=False,hardware_accessed=False,root_promoted=False,
    scope='Only the linker placement changes. Five full numerical object allocation/relocation payloads are identical; every surviving sized numerical function is identical or differs solely by calls to proven equivalent named functions. The listed V121 correctness reports retain their original ELF hashes and apply via this explicit bridge. Fresh instruction/cache/runtime checks are separate. No identical XIP traffic or physical timing claim.')
(work/'equivalence.json').write_text(json.dumps(result,indent=2)+'\n')
print('PASS:',len(objects),'identical numerical objects;',len(kept),'linked functions;',len(moved),'relocated; numerical correctness evidence explicitly reused.')
