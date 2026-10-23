"""Audit V142's opaque-call substitution, unchanged numerical bodies and resources."""
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root = Path.cwd()
work = Path(__file__).resolve().parent
parent = root/'.build/m0-pow-horner-final-v138-20261023'
sys.path.insert(0, str(root/'tests'))
from check_stm32_vectors import ElfImage


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


ns = dict(ElfImage=ElfImage, struct=struct, hashlib=hashlib)
for node in ast.parse((root/'.build/m0-pow-stable-v87-20261022/link-equivalence.py').read_text()).body:
    if isinstance(node, ast.FunctionDef) and node.name in ('symbols', 'object_payload', 'payload', 'target'):
        exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), node.name, 'exec'), ns)
objects = []
functions = set()
function_sites = {}
call_replacements = []
for name in ('compact_math.cpp.o', 'native_eabi_m0.cpp.o', 'native_eabi_m0_cr.cpp.o',
             'native_eabi_m0.S.o', 'native_eabi_m0_rp2040.S.o'):
    paths = [next((p/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name)) for p in (parent, work)]
    before, after = [ns['object_payload'](p) for p in paths]
    for p in (before, after):
        p['allocated'] = {n: v for n, v in p['allocated'].items() if v}
    if name == 'native_eabi_m0.cpp.o':
        extra_alloc=set(after['allocated'])-set(before['allocated'])
        assert extra_alloc=={'.m0_pow_small_y_cold'},extra_alloc
        assert {n:v for n,v in after['allocated'].items() if n not in extra_alloc}==before['allocated'], 'Old numerical instruction bytes changed'
        transformed = {}
        for section, rows in before['relocations'].items():
            transformed[section] = []
            for row in rows:
                row = list(row)
                if section == '.rel.m0_pow_refine_extension' and row[2] == 'mk61_m0_cr_pow':
                    row[2] = 'mk61_m0_pow_tiny_or_cr'
                    call_replacements.append(dict(section=section, offset=row[0], relocation_type=row[1]))
                transformed[section].append(tuple(row))
        assert {n:v for n,v in after['relocations'].items() if n!='.rel.m0_pow_small_y_cold'}==transformed, 'Unexpected old numerical relocation change'
        assert call_replacements
    elif name == 'native_eabi_m0_rp2040.S.o':
        extra = set(after['allocated'])-set(before['allocated'])
        assert extra == {'.m0_pow_tiny_cold','.m0_pow_small_y_cold'}, extra
        assert {n: v for n, v in after['allocated'].items() if n not in extra} == before['allocated']
        extra_rel = set(after['relocations'])-set(before['relocations'])
        assert extra_rel == {'.rel.m0_pow_tiny_cold','.rel.m0_pow_small_y_cold'}
        assert {n: v for n, v in after['relocations'].items() if n not in extra_rel} == before['relocations']
        assert set(row[2] for row in after['relocations']['.rel.m0_pow_tiny_cold']) == {'mk61_m0_cr_pow','mk61_m0_pow_small_y'}
        assert [row[2] for row in after['relocations']['.rel.m0_pow_small_y_cold']]==['mk61_m0_pow_exp_product']
    else:
        assert before == after, name
    objects.append(dict(name=name, before_sha256=sha(paths[0]), after_sha256=sha(paths[1])))
    object_image=ElfImage(paths[0])
    for symbol in ns['symbols'](object_image):
        if not symbol['size'] or symbol['info']&15!=2:
            continue
        name=symbol['name'];functions.add(name)
        section=object_image.sections[symbol['index']]
        section_name=next(n for n,s in object_image.named_sections.items() if s is section)
        begin=symbol['value']&~1
        for row in before['relocations'].get('.rel'+section_name,[]):
            if row[1]==10 and begin<=row[0]<begin+symbol['size']:
                function_sites.setdefault(name,set()).add(row[0]-begin)

elf_path = work/'firmware/mk61s-picocalc-pico-h.elf'
before, after = [ElfImage(p/'firmware/mk61s-picocalc-pico-h.elf') for p in (parent, work)]
unchanged = []
relocated = []
refine_calls = []
veneer_prefix=bytes.fromhex('01b40248844601bc6047')

def resolved(image,address):
    symbols=[s for s in ns['symbols'](image) if s['info']&15==2 and (s['value']&~1)==address and 'veneer' in s['name']]
    if not symbols:
        return address
    assert all(s['size']==16 for s in symbols),symbols
    body=ns['payload'](image,address,16)
    assert body[:10]==veneer_prefix and body[10:12] in (bytes.fromhex('00bf'),bytes.fromhex('c046')),body.hex()
    pointer=struct.unpack_from('<I',body,12)[0]
    assert pointer&1
    return pointer&~1

for name in sorted(functions):
    assert (name in before.symbols) == (name in after.symbols), name
    if name not in before.symbols:
        continue
    address = before.symbols[name] & ~1
    size = before.sizes[name]
    assert after.symbols[name] == before.symbols[name] and after.sizes[name] == size, name
    a, b = [ns['payload'](e, address, size) for e in (before, after)]
    normalized = bytearray(b)
    equivalent_calls=[]
    for i in sorted(function_sites.get(name,set())):
        old_target = ns['target'](a[i:i+4], address+i)
        new_target = ns['target'](b[i:i+4], address+i)
        assert old_target is not None and new_target is not None,(name,i)
        old_resolved,new_resolved=resolved(before,old_target),resolved(after,new_target)
        if name=='pow_refine_checked' and old_resolved==before.symbols['mk61_m0_cr_pow']&~1 and new_resolved==after.symbols['mk61_m0_pow_tiny_or_cr']&~1:
            normalized[i:i+4]=a[i:i+4]
            refine_calls.append(dict(address=hex(address+i), old_target=hex(old_target), new_target=hex(new_target)))
        else:
            assert old_resolved==new_resolved,(name,i,hex(old_resolved),hex(new_resolved))
            if a[i:i+4]!=b[i:i+4]:
                normalized[i:i+4]=a[i:i+4]
                equivalent_calls.append(dict(address=hex(address+i),old_target=hex(old_target),new_target=hex(new_target),resolved_target=hex(old_resolved)))
    assert bytes(normalized) == a,('A changed byte is not a verified named BL relocation',name)
    if a==b:
        unchanged.append(name)
    elif name!='pow_refine_checked':
        relocated.append(dict(name=name,calls=equivalent_calls))
assert refine_calls

resources = ('__HeapLimit', '__StackBottom', '__StackTop', '__StackOneBottom', '__StackOneTop',
             '__scratch_y_start__', '__scratch_y_end__', '__end__')
for name in resources:
    assert after.symbols[name] == before.symbols[name], name
assert after.named_sections['.scratch_y'][5] == before.named_sections['.scratch_y'][5] == 4072
scratch_exact=after.bytes_at(after.named_sections['.scratch_y']) == before.bytes_at(before.named_sections['.scratch_y'])
from collections import Counter
scratch_veneer_targets=[]
for image in (before,after):
    seen=set();targets=[]
    section=image.named_sections['.scratch_y']
    for s in ns['symbols'](image):
        address=s['value']&~1
        if s['info']&15==2 and 'veneer' in s['name'] and section[3]<=address<section[3]+section[5] and address not in seen:
            seen.add(address);targets.append(resolved(image,address))
    scratch_veneer_targets.append(Counter(targets))
assert scratch_veneer_targets[0]==scratch_veneer_targets[1]
for name, size in [('pow_sqrt64_coefficients', 8192), ('_ZL15pow_rsqrt_seeds', 2048)]:
    assert after.symbols[name] == before.symbols[name]
    address = before.symbols[name]
    assert ns['payload'](before, address, size) == ns['payload'](after, address, size)
manifest = json.loads((work/'firmware/manifest.json').read_text())
assert manifest['static_ram_bytes'] == 198856 and manifest['flash_bytes'] == 1537008
assert after.named_sections['.m0_pow_tiny_cold'][3] == 0x1016B900
helper_bytes = after.named_sections['.m0_pow_tiny_cold'][5]
assert helper_bytes <= 0x9C
small_section=after.named_sections['.m0_pow_small_y_cold']
assert small_section[3]==0x1016AD00 and small_section[3]+small_section[5]<=0x1016B900
assert not re.search(r'libgcc[^\n]*\([^\n)]*\.o\)', (work/'build/mk61s-picocalc-pico-h.elf.map').read_text())
preparation = json.loads((work/'preparation.json').read_text())
files = {str(p.relative_to(work/'source')): sha(p) for p in sorted((work/'source').rglob('*'))
         if p.is_file() and '__pycache__' not in p.parts}
assert files == preparation['source_file_hashes'] and len(files) == 646
report = dict(status='PASS_ORIGINAL_OBJECTS_AND_VERIFIED_VENEER_BL_EQUIVALENCE',
              build=manifest['build_id'], source_sha256=manifest['source_sha256'], elf_sha256=sha(elf_path),
              modified_vs_V138=['code/native_eabi_m0_pow_fast.inc','code/native_eabi_m0_rp2040.S','ports/picocalc/m0_math_extension.ld'], added_files=[], objects=objects,
              original_numerical_object_instructions_and_tables_identical=True,
              only_old_object_relocation_changes=call_replacements,
              unchanged_numerical_linked_functions=len(unchanged), unchanged_names=unchanged,
              only_equivalent_BL_relocated_numerical_functions=relocated,
              linked_equivalence_scope='Every changed non-pow_refine byte is a THM_CALL relocation already present in the old object. Both veneers match the5-instruction register-preserving pattern and resolve to the identical original function address. Original function addresses/sizes and instruction counts remain stable; XIP/cache traffic and physical cycles are separate.',
              sole_changed_old_function='pow_refine_checked', only_linked_call_changes=refine_calls,
              helper_bytes=helper_bytes, helper_address='0x1016B900', small_y_code_bytes=small_section[5], new_allocated_Flash_bytes=helper_bytes+small_section[5],
              main_static_RAM_bytes=198856, heap_bytes=30520, scratch_bytes=4072,
              complete_scratch_code_byte_identical=scratch_exact, scratch_veneer_target_multiset_identical=True, image_extent_bytes=1537008,
              additional_global_RAM=0, additional_scratch_code=0, new_tables=0,
              existing_root_and_inverse_tables_byte_identical=True, libgcc_archive_members=0,
              producer_sha256=sha(__file__), hardware_accessed=False, production_promoted=False,
              scope='All previous numerical object instruction/data payloads remain exact. One cold call target changes semantically; other linked BL differences are independently verified equivalent veneers. New certified small-y code and a private Thumb thunk occupy existing Flash gaps. Physical cache/cycle acceptance is still required.',
              goal_complete=False)
(work/'validation.json').write_text(json.dumps(report, indent=2)+'\n')
print('PASS:',len(unchanged),'exact linked math bodies;',len(relocated),'with only equivalent BL changes;',len(refine_calls),'cold target change;',helper_bytes+small_section[5],'new Flash bytes; RAM unchanged. Physical cycles pending.',flush=True)
