"""Compile only runtime objects and audit all unaffected allocated sections."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
commands=[]
def compile(src,out,rp=True,cpu='cortex-m0plus',hard=False,use=True):
    cpp=src.suffix=='.cpp';compiler='arm-none-eabi-g++' if cpp else 'arm-none-eabi-gcc'
    cmd=[str(CC/compiler),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),'-Os','-I',str(P)]
    if cpp:cmd+=['-std=gnu++17','-fno-exceptions','-fno-rtti','-ffunction-sections','-fdata-sections','-fno-builtin']
    if use:cmd+=['-DMK61_USE_M0_EABI=1']
    if rp:cmd+=['-DMK61_M0_RP2040_EABI=1']
    if hard:cmd+=['-mfpu=fpv4-sp-d16']
    cmd+=['-c',str(src),'-o',str(out)]
    subprocess.run(cmd,check=True);commands.append(cmd);return ElfImage(out)
def payload(e):
    return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
asm_old=compile(P/'native_eabi_m0.S',W/'control-assembly.o')
asm_new=compile(W/'native_eabi_m0.S',W/'candidate-assembly.o')
a,b=payload(asm_old),payload(asm_new)
added=set(b)-set(a);removed=set(a)-set(b);changed=[k for k in a.keys()&b.keys() if a[k]!=b[k]]
assert added=={'.text.__aeabi_d2uiz'} and not removed and not changed,(added,removed,changed)
diag=ElfImage(W/'candidate.elf')
assert b['.text.__aeabi_d2uiz']==diag.bytes_at(diag.named_sections['.text'])
cpp_old=compile(P/'native_eabi_m0.cpp',W/'control-cpp.o')
cpp_new=compile(W/'native_eabi_m0.cpp',W/'candidate-cpp.o')
ca,cb=payload(cpp_old),payload(cpp_new)
cpp_added=set(cb)-set(ca);cpp_removed=set(ca)-set(cb)
cpp_changed=sorted(k for k in ca.keys()&cb.keys() if ca[k]!=cb[k])
assert cpp_removed=={'.text.__aeabi_d2uiz'} and not cpp_added and not cpp_changed,(cpp_added,cpp_removed,cpp_changed)
contexts=[]
for label,cpu,hard,use in [('generic_M0','cortex-m0plus',False,True),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',True,False)]:
    for suffix in ('S','cpp'):
        name='native_eabi_m0.'+suffix
        before=compile(P/name,W/(label+'-'+suffix+'-control.o'),False,cpu,hard,use)
        after=compile(W/name,W/(label+'-'+suffix+'-candidate.o'),False,cpu,hard,use)
        assert payload(before)==payload(after),(label,suffix)
    contexts.append(dict(context=label,allocated_assembly_and_cpp_identical=True))
patch=''
for name in ('native_eabi_m0_convert.inc','native_eabi_m0.cpp'):
    patch+=''.join(difflib.unified_diff((P/name).read_text().splitlines(True),(W/name).read_text().splitlines(True),fromfile='V164/code/'+name,tofile='candidate/code/'+name))
(W/'unsigned32-only.patch').write_text(patch)
report=dict(status='PASS_ONLY_RP2040_UINT32_IMPLEMENTATION_REPLACED',assembly_added_sections=sorted(added),assembly_other_allocated_sections_identical=True,
    cpp_removed_sections=sorted(cpp_removed),cpp_other_allocated_sections_identical=True,
    diagnostic_and_public_assembly_body_byte_identical=True,
    old_cpp_leaf_section_bytes=len(ca['.text.__aeabi_d2uiz']),new_assembly_section_bytes=len(b['.text.__aeabi_d2uiz']),
    combined_object_section_bytes_delta=len(b['.text.__aeabi_d2uiz'])-len(ca['.text.__aeabi_d2uiz']),contexts=contexts,commands=commands,
    compiler_scope='Unlinked -Os controls, not a new production ELF. Host C++ function retained even when the RP flag is set.',
    canonical_or_frozen_changed=False,USB_accessed=False,goal_complete=False)
(W/'isolation.json').write_text(json.dumps(report,indent=2)+'\n')
build=json.loads((W/'build.json').read_text())
for n in build['files']:build['files'][n]=hashlib.sha256((W/n).read_bytes()).hexdigest()
(W/'build.json').write_text(json.dumps(build,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
