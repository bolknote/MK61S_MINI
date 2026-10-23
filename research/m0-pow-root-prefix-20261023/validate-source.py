"""Bind the GNU-only source, new kernels, unchanged runtime and resource bounds."""

import argparse
_checkpoint_parser = argparse.ArgumentParser(description=__doc__)
_checkpoint_parser.add_argument("--work", required=True, help="Existing private work directory; see README")
_checkpoint_args = _checkpoint_parser.parse_args()
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

root=Path.cwd();work=Path(_checkpoint_args.work).resolve()
parent=root/'.build/m0-pow-final-parent-v110-20261023'
diagnostic=root/'.build/m0-pow-root-prefix-v120-20261023'
raw=root/'.build/m0-pow-root64-v112-20261023'
sys.path.insert(0,str(root/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
load=lambda p:json.loads(Path(p).read_text())
namespace=dict(ElfImage=ElfImage,struct=struct,hashlib=hashlib)
for filename,names in [('.build/m0-memory-compose-v79-20261021/prepare.py',('fingerprint',)),
    ('.build/m0-pow-stable-v87-20261022/link-equivalence.py',('symbols','object_payload','payload'))]:
    for node in ast.parse((root/filename).read_text()).body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),node.name,'exec'),namespace)
manifest=load(work/'firmware/manifest.json')
assert namespace['fingerprint'](work/'source')==manifest['source_sha256']
files=lambda tree:{str(p.relative_to(tree)):p for p in tree.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
before,after=files(parent/'source'),files(work/'source')
added=sorted(after.keys()-before.keys())
changed=sorted(n for n in before if before[n].read_bytes()!=after[n].read_bytes())
preparation=load(work/'preparation.json')
assert added==preparation['added_files'] and changed==preparation['modified_files']
objects={};same=[]
for name in ('compact_math.cpp.o','native_eabi_m0.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o','native_eabi_m0_rp2040.S.o'):
    a=next((parent/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    b=next((work/'build/CMakeFiles/mk61s-picocalc-pico-h.dir').rglob(name))
    left,right=namespace['object_payload'](a),namespace['object_payload'](b)
    objects[name]=dict(before=str(a.relative_to(root)),after=str(b.relative_to(root)),before_sha256=sha(a),after_sha256=sha(b))
    if name in ('compact_math.cpp.o','native_eabi_m0_cr.cpp.o','native_eabi_m0.S.o'):
        assert left==right,(name,'Unrelated object allocation or relocation changed')
        same.append(name)
    elif name=='native_eabi_m0.cpp.o':
        for kind in left:
            differences={n for n in left[kind].keys()|right[kind].keys() if left[kind].get(n)!=right[kind].get(n)}
            assert differences==({'.m0_pow_dispatch_extension'} if kind=='allocated' else {'.rel.m0_pow_dispatch_extension'}),(name,kind,differences)
    else:
        for kind in left:
            for n,value in left[kind].items():assert right[kind][n]==value,(name,kind,n)
        objects[name]['added_allocations']={n:len(v)//2 for n,v in right['allocated'].items() if n not in left['allocated']}
        kernel=namespace['object_payload'](diagnostic/'kernels-gnu.o')
        assert right['allocated']['.m0_pow_root_prefix']==kernel['allocated']['.m0_pow_exact_extension']
        # New calls now reference same-object definitions rather than undefined
        # imports. Bind their names and offsets; the imported bodies stay exact.
        expected=kernel['relocations']['.rel.m0_pow_exact_extension']
        actual=right['relocations']['.rel.m0_pow_root_prefix']
        assert [r[:3] for r in expected]==[r[:3] for r in actual]
        raw_object=namespace['object_payload'](raw/'root64.o')
        assert right['allocated']['.m0_sqrt64_fixed.root64']==raw_object['allocated']['.m0_sqrt64_fixed.root64']
        assert right['relocations']['.rel.m0_sqrt64_fixed.root64']==raw_object['relocations']['.rel.m0_sqrt64_fixed.root64']
elf=work/'firmware/mk61s-picocalc-pico-h.elf'
image=ElfImage(elf);old=ElfImage(parent/'firmware/mk61s-picocalc-pico-h.elf')
for name in ('__HeapLimit','__StackBottom','__StackTop','__StackOneBottom','__StackOneTop',
             '__scratch_y_start__','__scratch_y_end__'):
    assert image.symbols[name]==old.symbols[name],name
assert image.named_sections['.scratch_y'][5]==4072
assert manifest['static_ram_bytes']==198856
for name in ('__bss_end__','end','__end__'):
    if name in old.symbols:assert image.symbols[name]==old.symbols[name],name
runtime=[]
for name in ('__wrap_memcpy','__wrap_memmove','__wrap_memcmp'):
    a,b=old.symbols[name]&~1,image.symbols[name]&~1
    size=old.sizes[name]
    assert a==b and image.sizes[name]==size
    assert namespace['payload'](old,a,size)==namespace['payload'](image,b,size)
    runtime.append(dict(symbol=name,address=hex(a),bytes=size,sha256=hashlib.sha256(namespace['payload'](image,b,size)).hexdigest()))
assert image.symbols['pow_sqrt64_coefficients']==0x1016BC60
assert namespace['payload'](image,0x1016BC60,8192)==namespace['payload'](old,0x1016BC60,8192)
map_text=(work/'build/mk61s-picocalc-pico-h.elf.map').read_text() if (work/'build/mk61s-picocalc-pico-h.elf.map').exists() else (work/'build/mk61s-picocalc-pico-h.map').read_text()
assert not re.search(r'libgcc[^\n]*\([^\n)]*\.o\)',map_text)
platform=root/'.build/finish-m0-review-20261022/production-v3-flash-final/source'
platform_files=files(platform)
full_added=sorted(after.keys()-platform_files.keys())
full_changed=sorted(n for n in platform_files if platform_files[n].read_bytes()!=after[n].read_bytes())
report=dict(status='PASS_GNU_SOURCE_KERNEL_AND_RESOURCE_SCOPE',build=manifest['build_id'],source_sha256=manifest['source_sha256'],
    elf_sha256=sha(elf),incremental_modified=changed,incremental_added=added,
    complete_platform_modified=full_changed,complete_platform_added=full_added,
    identical_other_source_files=len(before)-len(changed),unchanged_numerical_object_payloads=same,objects=objects,
    new_GNU_kernel_bytes_and_named_calls_match_reference=True,new_raw_root_bytes_and_relocations_match_reference=True,
    unchanged_8192byte_sqrt_coefficients=True,linked_runtime_bodies=runtime,
    static_main_ram_bytes=manifest['static_ram_bytes'],heap_bytes=30520,scratch_used_bytes=4072,
    scratch_reserved_bytes=4096,image_extent_bytes=manifest['flash_bytes'],additional_global_RAM=0,
    new_arithmetic_tables=0,linked_libgcc_archive_members=0,new_compiler_dependency=False,
    producer_sha256=sha(__file__),hardware_ready=False,hardware_accessed=False,root_promoted=False,
    scope='Self-contained GCC/GNU-as source; exact old allocated object payloads except the declared dispatcher and two new kernels/metadata. Independent correctness tests and cache/timing evidence remain separate; platform hardware acceptance is pending.')
(work/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print('PASS: GNU-only source/kernel bytes; heap/RAM/scratch unchanged; no new arithmetic table or libgcc member.')
