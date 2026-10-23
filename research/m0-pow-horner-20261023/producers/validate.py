"""Audit the exact source, GNU kernels, alias storage and fixed runtime slots."""
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
root=Path.cwd();work=Path(__file__).resolve().parent
parent=root/'.build/m0-pow-root-prefix-v122-20261023'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
namespace=dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for filename,names in [('.build/m0-memory-compose-v79-20261021/prepare.py',('fingerprint',)),
    ('.build/m0-pow-stable-v87-20261022/link-equivalence.py',('symbols','object_payload','payload'))]:
    for node in ast.parse((root/filename).read_text()).body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),namespace)
manifest=json.loads((work/'firmware/manifest.json').read_text())
assert namespace['fingerprint'](work/'source')==manifest['source_sha256']
files=lambda tree:{str(p.relative_to(tree)):p for p in tree.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
old_files,new_files=files(parent/'source'),files(work/'source')
assert old_files.keys()==new_files.keys() and len(new_files)==646
changed=sorted(n for n in old_files if old_files[n].read_bytes()!=new_files[n].read_bytes())
assert changed==json.loads((work/'preparation.json').read_text())['modified_files']
objects=[];same=[];functions=set()
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    before=next((parent/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    after=next((work/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    a,b=namespace['object_payload'](before),namespace['object_payload'](after)
    a['allocated']={n:v for n,v in a['allocated'].items() if v}
    b['allocated']={n:v for n,v in b['allocated'].items() if v}
    if name!='native_eabi_m0_rp2040.S.o':
        assert a==b,(name,'Unrelated numerical allocations or relocations changed')
        same.append(name)
    else:
        allowed={'.m0_pow_root_prefix','.m0_pow_square_fixed','.m0_pow_near_one_refine',
                 '.m0_sqrt64_fixed.root64','.m0_pow_boundary_exact','.m0_pow_tail_extra'}
        allowed|={'.ARM.exidx'+n for n in list(allowed)}
        # Horner starts from the exact input; the negative accumulator is
        # assigned at its first selected term. No identity initializer remains.
        assert '.rodata.cst16' not in b['allocated']
        allowed.add('.rodata.cst16')
        for n in a['allocated'].keys()|b['allocated'].keys():
            if a['allocated'].get(n)!=b['allocated'].get(n):assert n in allowed,n
        for n in a['relocations'].keys()|b['relocations'].keys():
            if a['relocations'].get(n)!=b['relocations'].get(n):assert n.removeprefix('.rel') in allowed,n
        reference=namespace['object_payload'](work/'kernels-gnu.o')
        assert '.rodata.cst16' not in reference['allocated']
        for n,value in reference['allocated'].items():
            if value and n.startswith(('.m0_', '.ARM.exidx')):assert b['allocated'][n]==value,n
        for n,rows in reference['relocations'].items():
            assert [r[:3] for r in b['relocations'][n]]==[r[:3] for r in rows],n
        raw=namespace['object_payload'](work/'root64.o')
        assert b['allocated']['.m0_sqrt64_fixed.root64']==raw['allocated']['.m0_sqrt64_fixed.root64']
        assert b['relocations']['.rel.m0_sqrt64_fixed.root64']==raw['relocations']['.rel.m0_sqrt64_fixed.root64']
    objects.append(dict(name=name,before_sha256=sha(before),after_sha256=sha(after)))
    for symbol in namespace['symbols'](ElfImage(before)):
        name=symbol['name']
        if symbol['size'] and symbol['info']&15==2 and not any(word in name.lower() for word in ('pow','root64','root128')):
            functions.add(name)
old_path=parent/'firmware/mk61s-picocalc-pico-h.elf';elf=work/'firmware/mk61s-picocalc-pico-h.elf'
before,after=ElfImage(old_path),ElfImage(elf)
unchanged=[]
for name in sorted(functions):
    assert (name in before.symbols)==(name in after.symbols),name
    if name not in before.symbols:continue
    address=before.symbols[name]&~1;size=before.sizes[name]
    assert after.symbols[name]==before.symbols[name] and after.sizes[name]==size,(name,'Unrelated function moved')
    assert namespace['payload'](before,address,size)==namespace['payload'](after,address,size),(name,'Unrelated function bytes changed')
    unchanged.append(name)
runtime=[]
for name in ('__wrap_memcpy','__wrap_memmove','__wrap_memcmp'):
    address=before.symbols[name]&~1;size=before.sizes[name]
    assert after.symbols[name]==before.symbols[name] and after.sizes[name]==size
    a,b=namespace['payload'](before,address,size),namespace['payload'](after,address,size)
    assert a==b,name
    runtime.append(dict(name=name,address=hex(address),bytes=size,sha256=hashlib.sha256(b).hexdigest()))
for name in ('__HeapLimit','__StackBottom','__StackTop','__StackOneBottom','__StackOneTop','__scratch_y_start__','__scratch_y_end__'):
    assert after.symbols[name]==before.symbols[name],name
assert after.named_sections['.scratch_y'][5]==4072
assert manifest['static_ram_bytes']==198856 and manifest['flash_bytes']==1537008
for name,size in [('pow_sqrt64_coefficients',8192),('_ZL15pow_rsqrt_seeds',2048)]:
    assert after.symbols[name]==before.symbols[name],name
    address=before.symbols[name]
    assert namespace['payload'](before,address,size)==namespace['payload'](after,address,size),name
assert after.symbols['factor_rsqrt_seeds']==after.symbols['_ZL15pow_rsqrt_seeds']==0x10161580
assert after.named_sections['.m0_pow_boundary_fixed'][3]==0x10150000
assert after.named_sections['.m0_pow_boundary_fixed'][5]<=0x280
assert after.named_sections['.m0_pow_tail_fixed'][3]==0x10150280
assert sum(after.named_sections['.m0_pow_tail_fixed'][i] for i in (3,5))<=0x10150D00
assert after.symbols['pow_sqrt64_raw']&~1==0x1014DE60
map_path=work/'build/mk61s-picocalc-pico-h.elf.map'
if not map_path.exists():map_path=work/'build/mk61s-picocalc-pico-h.map'
assert not re.search(r'libgcc[^\n]*\([^\n)]*\.o\)',map_path.read_text())
platform=root/'.build/finish-m0-review-20261022/production-v3-flash-final/source'
platform_files=files(platform)
full_added=sorted(new_files.keys()-platform_files.keys())
full_changed=sorted(n for n in platform_files if platform_files[n].read_bytes()!=new_files[n].read_bytes())
record=dict(status='PASS_GNU_SOURCE_KERNEL_ALIAS_AND_RESOURCE_SCOPE',build=manifest['build_id'],source_sha256=manifest['source_sha256'],
    elf_sha256=sha(elf),modified_vs_V122=changed,added_vs_V122=[],
    full_platform_modified=full_changed,full_platform_added=full_added,
    unchanged_numerical_object_allocations_and_relocations=same,objects=objects,
    unchanged_non_pow_linked_functions=len(unchanged),unchanged_non_pow_names=unchanged,
    raw_and_full128_GNU_bytes_and_named_calls_match_reference=True,
    existing_8192byte_root_and_2048byte_inverse_tables_unchanged=True,
    inverse_seed_alias_address='0x10161580',inverse_seed_alias_additional_storage_bytes=0,
    linked_runtime_bodies=runtime,static_main_RAM_bytes=198856,heap_bytes=30520,scratch_used_bytes=4072,
    image_extent_bytes=1537008,new_tables=0,additional_global_RAM=0,linked_libgcc_archive_members=0,
    additional_immutable_Root64_identity_bytes=0,
    new_compiler_dependency=False,producer_sha256=sha(__file__),hardware_accessed=False,root_promoted=False,
    scope='Exact final source fingerprint and five-file incremental scope; four full numerical object payloads unchanged; new shared kernels match GNU reference bytes/calls; existing tables/runtime/heap/stack/scratch preserved. Independent numerical tests, cache models and physical hardware acceptance remain separate.')
(work/'validation.json').write_text(json.dumps(record,indent=2)+'\n')
print('PASS:',len(same),'unchanged numerical objects;',len(unchanged),'non-pow linked bodies; zero-storage alias and fixed resources.',flush=True)
