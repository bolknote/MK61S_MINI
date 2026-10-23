"""Check the private exp-only delta and all other numerical body/veneer targets."""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
parent = root/'.build/m0-pow-small-y-stable-v144-20261023'
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


ns = dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for node in ast.parse((root/'.build/m0-pow-stable-v87-20261022/link-equivalence.py').read_text()).body:
    if isinstance(node,ast.FunctionDef) and node.name in ('symbols','object_payload','payload','target'):
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),ns)
functions = set()
sites = {}
objects = []
external_exp_calls = []
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o',
             'native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    paths = [next((p/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name)) for p in (parent,work)]
    before,after = [ns['object_payload'](p) for p in paths]
    for d in (before,after):
        d['allocated'] = {n:v for n,v in d['allocated'].items() if v}
    oi = ElfImage(paths[0])
    if name=='native_eabi_m0.cpp.o':
        assert set(after['allocated'])-set(before['allocated'])=={'.m0_exp_endpoints'}
        assert {n:v for n,v in before['allocated'].items() if n!='.m0_exp_core'} == {n:v for n,v in after['allocated'].items() if n not in ('.m0_exp_core','.m0_exp_endpoints')}
        assert {n:v for n,v in before['relocations'].items() if n!='.rel.m0_exp_core'} == {n:v for n,v in after['relocations'].items() if n not in ('.rel.m0_exp_core','.rel.m0_exp_endpoints')}
        begin = oi.symbols['mk61_m0_exp']&~1
        assert before['allocated']['.m0_exp_core'][:begin*2] == after['allocated']['.m0_exp_core'][:begin*2]
        assert [r for r in before['relocations']['.rel.m0_exp_core'] if r[0]<begin] == [r for r in after['relocations']['.rel.m0_exp_core'] if r[0]<begin]
    else:
        assert before==after,name
    objects.append(dict(name=name,before_sha256=sha(paths[0]),after_sha256=sha(paths[1])))
    for s in ns['symbols'](oi):
        if not s['size'] or s['info']&15!=2:
            continue
        n=s['name'];functions.add(n)
        section=oi.sections[s['index']]
        section_name=next(n for n,v in oi.named_sections.items() if v is section)
        begin=s['value']&~1
        for r in before['relocations'].get('.rel'+section_name,[]):
            if begin<=r[0]<begin+s['size']:
                if r[1]==10:
                    sites.setdefault(n,set()).add(r[0]-begin)
                if r[2] in ('mk61_m0_exp','_ZN12compact_math3expEd'):
                    external_exp_calls.append(dict(caller=n,target=r[2]))
assert not external_exp_calls,external_exp_calls

old,new = [ElfImage(p/'firmware/mk61s-picocalc-pico-h.elf') for p in (parent,work)]
veneer_prefix=bytes.fromhex('01b40248844601bc6047')


def resolved(image,address):
    matches=[s for s in ns['symbols'](image) if s['info']&15==2 and (s['value']&~1)==address and 'veneer' in s['name']]
    if not matches:
        return address
    assert all(s['size']==16 for s in matches)
    body=ns['payload'](image,address,16)
    assert body[:10]==veneer_prefix and body[10:12] in (bytes.fromhex('00bf'),bytes.fromhex('c046'))
    pointer=struct.unpack_from('<I',body,12)[0]
    assert pointer&1
    return pointer&~1


unchanged=[];equivalent=[]
for name in sorted(functions):
    assert (name in old.symbols)==(name in new.symbols),name
    if name not in old.symbols:
        continue
    assert old.symbols[name]==new.symbols[name],name
    if name in ('mk61_m0_exp','_ZN12compact_math3expEd'):
        continue
    size=old.sizes[name]
    assert new.sizes[name]==size,name
    address=old.symbols[name]&~1
    a,b=[ns['payload'](e,address,size) for e in (old,new)]
    normalized=bytearray(b);calls=[]
    for i in sorted(sites.get(name,set())):
        ot=ns['target'](a[i:i+4],address+i);nt=ns['target'](b[i:i+4],address+i)
        assert ot is not None and nt is not None
        assert resolved(old,ot)==resolved(new,nt),(name,i,hex(ot),hex(nt))
        if a[i:i+4]!=b[i:i+4]:
            normalized[i:i+4]=a[i:i+4]
            calls.append(dict(address=hex(address+i),before=hex(ot),after=hex(nt),resolved=hex(resolved(old,ot))))
    assert bytes(normalized)==a,('Unexpected changed byte',name)
    (unchanged if a==b else equivalent).append(name if a==b else dict(name=name,calls=calls))

for name in ('__HeapLimit','__StackBottom','__StackTop','__StackOneBottom','__StackOneTop',
             '__scratch_y_start__','__scratch_y_end__','__end__'):
    assert new.symbols[name]==old.symbols[name],name
assert new.named_sections['.scratch_y'][5]==old.named_sections['.scratch_y'][5]==4072
targets=[]
for image in (old,new):
    section=image.named_sections['.scratch_y'];seen=set();values=[]
    for s in ns['symbols'](image):
        address=s['value']&~1
        if s['info']&15==2 and 'veneer' in s['name'] and section[3]<=address<section[3]+section[5] and address not in seen:
            seen.add(address);values.append(resolved(image,address))
    targets.append(Counter(values))
assert targets[0]==targets[1]
manifest=json.loads((work/'firmware/manifest.json').read_text())
assert manifest['static_ram_bytes']==198856
assert manifest['flash_bytes']==1537400
assert not re.search(r'libgcc[^\n]*\([^\n)]*\.o\)',(work/'build/mk61s-picocalc-pico-h.elf.map').read_text())
prep=json.loads((work/'preparation.json').read_text())
actual={str(p.relative_to(work/'source')):sha(p) for p in (work/'source').rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual==prep['source_file_hashes'] and len(actual)==646
endpoint_bytes=new.sizes['mk61_m0_exp_endpoint']
exp_delta=new.sizes['mk61_m0_exp']-old.sizes['mk61_m0_exp']
report=dict(status='PASS_EXP_ONLY_OBJECT_DELTA_AND_OTHER_BODY_VENEER_EQUIVALENCE',
    build=manifest['build_id'],source_sha256=manifest['source_sha256'],
    elf_sha256=sha(work/'firmware/mk61s-picocalc-pico-h.elf'),objects=objects,
    modified_vs_V144=prep['modified_files'],unchanged_numerical_linked_functions=len(unchanged),
    unchanged_names=unchanged,only_equivalent_BL_relocated_functions=equivalent,
    changed_function='mk61_m0_exp /compact_math::exp alias',exp_entry_address=hex(new.symbols['mk61_m0_exp']&~1),
    original_exp_entry_address_identical=True,old_exp_bytes=old.sizes['mk61_m0_exp'],
    new_exp_bytes=new.sizes['mk61_m0_exp'],exp_code_delta_bytes=exp_delta,
    endpoint_helper_bytes=endpoint_bytes,new_allocated_Flash_bytes=exp_delta+endpoint_bytes,
    other_object_instruction_and_data_payloads_identical=True,
    numerical_exp_calls_outside_public_entry=external_exp_calls,
    main_static_RAM_bytes=198856,heap_bytes=30520,scratch_bytes=4072,image_extent_bytes=1537400,
    complete_scratch_code_byte_identical=old.bytes_at(old.named_sections['.scratch_y'])==new.bytes_at(new.named_sections['.scratch_y']),
    scratch_veneer_target_multiset_identical=True,new_tables=0,new_global_RAM=0,libgcc_archive_members=0,
    producer_sha256=sha(__file__),hardware_accessed=False,production_promoted=False,
    scope='Only the existing exp body and the new endpoint helper change numerical semantics. Every other linked numerical body is exact or differs only at verified equivalent old BL relocations. Object tables are exact; no other numerical function calls public exp. Physical cache/cycle behavior is unmeasured.',goal_complete=False)
(work/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS:',len(unchanged),'exact other numerical bodies;',len(equivalent),'with verified equivalent BLs;exp delta',exp_delta,'+endpoint',endpoint_bytes,'bytes;RAM unchanged.')
