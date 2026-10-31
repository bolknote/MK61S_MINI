#!/usr/bin/env python3
"""Prepare a compatible memchr runtime prototype in an isolated source tree.

Never edits the shared checkout. Kernel selection remains provisional until
the device measurements; the patch is reviewable before any firmware install.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--words',type=int,choices=(1,4,8,16),default=16)
p.add_argument('--family',choices=('word','pair','fast','balanced','dsp'),default='word')
p.add_argument('--compact-f401',action='store_true')
a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
assert a.family=='word' or a.words>=4,'Pair variants need at least two pairs'
assert a.family!='dsp' or a.words in (4,8),'CBNZ forward branches are bounded to the measured16/32-byte blocks'
assert source!=ROOT and ROOT/'.build' in source.parents,'Use a dedicated .build source snapshot'
assert source.relative_to(ROOT/'.build').parts[0].startswith('memchr-'),'Use this experiment\'s own snapshot'
out.mkdir(parents=True,exist_ok=True)
originals={}
def edit(name,old,new,count=1):
    path=source/name;text=path.read_text()
    originals.setdefault(name,text)
    assert text.count(old)==count,(name,'unexpected source',old[:80],text.count(old))
    path.write_text(text.replace(old,new))
def create(name,text):
    path=source/name;assert not path.exists(),name
    originals[name]='';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)

edit('code/loadable_system_runtime.def','MK61_RUNTIME(__aeabi_dadd)',
    '#ifndef MK61_RUNTIME_OPTIONAL_ISO_C\n#define MK61_RUNTIME_OPTIONAL_ISO_C(name, result, ...) MK61_RUNTIME_ISO_C(name, result, __VA_ARGS__)\n#define MK61_RUNTIME_OPTIONAL_ISO_C_DEFAULT\n#endif\nMK61_RUNTIME(__aeabi_dadd)')
edit('code/loadable_system_runtime.def','MK61_RUNTIME_ISO_C(memcmp, int, const void*, const void*, size_t)',
    'MK61_RUNTIME_ISO_C(memcmp, int, const void*, const void*, size_t)\nMK61_RUNTIME_OPTIONAL_ISO_C(memchr, void*, const void*, int, size_t)\n#ifdef MK61_RUNTIME_OPTIONAL_ISO_C_DEFAULT\n#undef MK61_RUNTIME_OPTIONAL_ISO_C_DEFAULT\n#undef MK61_RUNTIME_OPTIONAL_ISO_C\n#endif')
edit('code/loadable_app_services.h','  MK61_RUNTIME_COUNT\n};','  MK61_RUNTIME_COUNT\n};\n/* The original table has 26 mandatory slots, independent of later additions. */\nenum { MK61_RUNTIME_BASE_COUNT = 26 };')
edit('code/loadable_app_services.h','  const mk61_service_runtime_function* runtime;\n} mk61_app_services;',
    '  const mk61_service_runtime_function* runtime;\n  /* Optional append-only tail. Old service-v2 providers end before this field. */\n  uint32_t runtime_count;\n} mk61_app_services;\n\n#define MK61_APP_SERVICES_BASE_SIZE (offsetof(mk61_app_services, runtime) + sizeof(((mk61_app_services*)0)->runtime))\nstatic inline uint32_t mk61_app_runtime_count(const mk61_app_services* services) {\n  if(!services || !services->runtime) return 0;\n  if(services->struct_size >= offsetof(mk61_app_services, runtime_count) + sizeof(services->runtime_count))\n    return services->runtime_count;\n  return MK61_RUNTIME_BASE_COUNT;\n}')
edit('code/loadable_app_services.h','services->struct_size < sizeof(*services)',
    'services->struct_size < MK61_APP_SERVICES_BASE_SIZE')
edit('sdk/portable/shared_runtime.c','  for(uint32_t i = 0; i < MK61_RUNTIME_COUNT; ++i)',
    '  if(mk61_app_runtime_count(services) < MK61_RUNTIME_BASE_COUNT) return 0;\n  for(uint32_t i = 0; i < MK61_RUNTIME_BASE_COUNT; ++i)')
edit('sdk/portable/system/system_compat.cpp','  for(u32 i = 0; i < MK61_RUNTIME_COUNT; ++i) if(!sys->runtime[i]) return false;',
    '  if(mk61_app_runtime_count(sys) < MK61_RUNTIME_BASE_COUNT) return false;\n  for(u32 i = 0; i < MK61_RUNTIME_BASE_COUNT; ++i) if(!sys->runtime[i]) return false;')
edit('sdk/portable/system/runtime.S','#define MK61_RUNTIME(name) runtime_trampoline name',
    '.macro runtime_optional_trampoline name\n.section .text.\\name, "ax", %progbits\n.global \\name\n.type \\name, %function\n.thumb_func\n\\name:\n ldr r3, =mk61_optional_\\name\n ldr r3, [r3]\n bx r3\n .ltorg\n.size \\name, .-\\name\n.set runtime_slot, runtime_slot + 4\n.endm\n#define MK61_RUNTIME_OPTIONAL_ISO_C(name, result, ...) runtime_optional_trampoline name\n#define MK61_RUNTIME(name) runtime_trampoline name')
edit('code/loadable_system_api.cpp','      runtime\n  };','      runtime, MK61_RUNTIME_COUNT\n  };')
edit('ports/picocalc/native_app.cpp','                                              native_runtime};',
    '                                              native_runtime, MK61_RUNTIME_COUNT};')
edit('ports/picocalc/native_app.cpp','                                              nullptr};',
    '                                              nullptr, 0};')
edit('ports/picocalc/CMakeLists.txt','foreach(MK61_MEM_OP memcpy memset memmove ',
    'foreach(MK61_MEM_OP memcpy memset memmove memchr ')

if a.family=='word':
    assembly=(HERE/'candidates.S').read_text()
    assembly=assembly[assembly.index('.macro probe'):assembly.index('.altmacro')]
    assembly=assembly.replace('function \\name\n','').replace('end \\name\n','')
    assembly=assembly.replace('probe','mk61_search_probe').replace('hit name','mk61_search_hit name').replace('hit \\name','mk61_search_hit \\name')
    purge=['mk61_search_probe','mk61_search_hit','mk61_search_body'];units=''
else:
    assembly=(HERE/'pair-candidates.S').read_text()
    assembly=assembly[assembly.index('.macro probe_pair'):assembly.index('search pair16,2')]
    assembly=assembly.replace('function \\name\n','').replace('.size \\name,.-\\name\n','')
    assembly=assembly.replace('defined(MEMCHR_FAST_PREFIX)','1' if a.family in ('fast','dsp') else '0')
    assembly=assembly.replace('defined(MEMCHR_BALANCED_PREFIX)','1' if a.family=='balanced' else '0')
    assembly=assembly.replace('defined(MEMCHR_CBNZ)','1' if a.family=='dsp' else '0')
    assembly=assembly.replace('probe_pair','mk61_search_pair')
    purge=['mk61_search_pair','mk61_search_body'];units='/2'
assembly=assembly.replace('.macro search ','.macro mk61_search_body ')
lines=['".syntax unified\\n"']
for line in assembly.splitlines():
    lines.append(line if line.startswith('#') else json.dumps(line+'\n'))
lines+=['".altmacro\\n"','"mk61_search_body mk61," MK61_MEMCHR_STRINGIFY(MK61_MEMCHR_WORDS) "'+units+'\\n"',
    '".noaltmacro\\n"',*['".purgem '+name+'\\n"' for name in purge],'".syntax divided\\n"']
create('code/memchr_arm.inc','/* Generated from the measured research candidates.S; exact spans only. */\n'+'\n'.join(lines)+'\n')
create('code/memory_search_arm.h','''#ifndef MK61_MEMORY_SEARCH_ARM_H
#define MK61_MEMORY_SEARCH_ARM_H
#include <stddef.h>
#ifndef MK61_MEMCHR_NAME
#define MK61_MEMCHR_NAME memchr
#endif
#ifndef MK61_MEMCHR_ATTRIBUTES
#define MK61_MEMCHR_ATTRIBUTES
#endif
#ifndef MK61_MEMCHR_WORDS
'''+('#if defined(STM32F401xC) || defined(STM32F401xE)\n#define MK61_MEMCHR_WORDS 4\n#else\n' if a.compact_f401 else '')+'''#define MK61_MEMCHR_WORDS '''+str(a.words)+('\n#endif' if a.compact_f401 else '')+'''
#endif
#if defined(__GNUC__) && !defined(__clang__) && (defined(__ARM_ARCH_6M__) || defined(__ARM_ARCH_7EM__))
#define MK61_MEMCHR_STRINGIFY_(value) #value
#define MK61_MEMCHR_STRINGIFY(value) MK61_MEMCHR_STRINGIFY_(value)
__attribute__((naked, noipa, aligned(4))) MK61_MEMCHR_ATTRIBUTES
void* MK61_MEMCHR_NAME(const void* data __attribute__((unused)),
    int value __attribute__((unused)),size_t size __attribute__((unused))) {
  __asm__(
#include "memchr_arm.inc"
  );
}
#undef MK61_MEMCHR_STRINGIFY
#undef MK61_MEMCHR_STRINGIFY_
#else
MK61_MEMCHR_ATTRIBUTES
void* MK61_MEMCHR_NAME(const void* data,int value,size_t size) {
  const unsigned char* bytes=(const unsigned char*)data;
  for(size_t i=0;i<size;++i) if(bytes[i]==(unsigned char)value) return (void*)(bytes+i);
  return NULL;
}
#endif
#endif
''')
start='/* Source-page NUL checks also need memchr.'
memory=(source/'sdk/portable/memory.c').read_text()
old=memory[memory.index(start):memory.index('\nint strcmp(')]
edit('sdk/portable/memory.c',old,'''/* Optional runtime memchr binds once, with an exact local fallback on old
 * 26-slot hosts. The initialized pointer and resolver are GC'd if unused. */
#ifdef MK61_APP_SHARED_RUNTIME
#include "loadable_app_services.h"
extern const mk61_app_api* mk61_api;
#define MK61_MEMCHR_NAME mk61_memchr_fallback
#endif
#include "memory_search_arm.h"
#ifdef MK61_APP_SHARED_RUNTIME
typedef void* (*mk61_memchr_function)(const void*,int,size_t);
static void* mk61_resolve_memchr(const void*,int,size_t);
mk61_memchr_function mk61_optional_memchr = mk61_resolve_memchr;
static void* mk61_resolve_memchr(const void* data,int value,size_t size) {
  const mk61_app_services* services=mk61_app_get_services(mk61_api,0);
  mk61_memchr_function selected=mk61_memchr_fallback;
  if(mk61_app_runtime_count(services)>MK61_RUNTIME_SLOT_memchr &&
      services->runtime[MK61_RUNTIME_SLOT_memchr])
    selected=(mk61_memchr_function)services->runtime[MK61_RUNTIME_SLOT_memchr];
  mk61_optional_memchr=selected;
  return selected(data,value,size);
}
#endif
''')
edit('code/system_memory.c','#define MK61_MEMCMP_M4_FLASH 1',
    '#include "native_libc.h"\n#if !MK61_USE_NATIVE_LIBC\n#include "memory_search_arm.h"\n#endif\n\n#define MK61_MEMCMP_M4_FLASH 1')
strings=(source/'code/system_strings.c').read_text()
old=strings[strings.index('void* memchr('):strings.index('size_t strlen(')]
edit('code/system_strings.c',old,'#include "memory_search_arm.h"\n')
edit('ports/picocalc/memory.c','#define MK61_MEMMOVE_NAME __wrap_memmove',
    '#define MK61_MEMCHR_NAME __wrap_memchr\n#define MK61_MEMCHR_ATTRIBUTES __attribute__((section(".time_critical.memchr")))\n#include "memory_search_arm.h"\n#define MK61_MEMMOVE_NAME __wrap_memmove')
edit('tests/portable_system_abi_self_test.c','_Static_assert(sizeof(mk61_system_api) == 28, "System API v1");',
    '_Static_assert(sizeof(mk61_system_api) == 32, "append-only runtime count");\n_Static_assert(MK61_APP_SERVICES_BASE_SIZE == 28, "old service prefix unchanged");\n_Static_assert(offsetof(mk61_system_api, runtime_count) == 28, "optional count tail");')
edit('tests/portable_system_abi_self_test.c','MK61_RUNTIME_COUNT == 26','MK61_RUNTIME_COUNT == 27 && MK61_RUNTIME_BASE_COUNT == 26')
edit('tests/app_services_self_test.c','  services.struct_size--;\n  assert(!mk61_app_get_services(&api, 0));\n  services.struct_size++;',
    '  services.struct_size=MK61_APP_SERVICES_BASE_SIZE-1;\n  assert(!mk61_app_get_services(&api, 0));\n  services.struct_size=sizeof(services);')
edit('tests/app_services_self_test.c','  services.runtime = runtime;',
    '  services.runtime = runtime;\n  services.runtime_count = MK61_RUNTIME_COUNT;')
edit('tests/portable_shared_runtime_memory_stubs.c','#include <string.h>',
    '#include <string.h>\n#include "loadable_app_services.h"\nconst mk61_app_api* mk61_api;')

patch=[]
for name,original in sorted(originals.items()):
    text=(source/name).read_text()
    patch.extend(difflib.unified_diff(original.splitlines(keepends=True),text.splitlines(keepends=True),
        fromfile='a/'+name if original else '/dev/null',tofile='b/'+name))
(out/'runtime-prototype.patch').write_text(''.join(patch))
(out/'runtime-prototype.json').write_text(json.dumps(dict(source=str(source),words=a.words,
    family=a.family,compact_f401=a.compact_f401,
    provisional_selection=True,hardware_tested=False,shared_checkout_changed=False,
    files={name:dict(before=hashlib.sha256(old.encode()).hexdigest() if old else None,
                    after=hashlib.sha256((source/name).read_bytes()).hexdigest()) for name,old in originals.items()}),indent=2)+'\n')
print('Prepared',len(originals),'isolated prototype files; hardware selection pending')
