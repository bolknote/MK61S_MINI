"""Public C++ object isolation, pinned resident bindings and M4 controls."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-atan-residual-original-goal-20261024'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
old=ElfImage(W/'control-full.o');new=ElfImage(W/'candidate-full.o');a,b=allocated(old),allocated(new)
added=set(b)-set(a);removed=set(a)-set(b);changed=[n for n in a.keys()&b.keys() if a[n]!=b[n]]
assert not added and not removed and changed==['.text.atan_fast'],(added,removed,changed)
original_object=BASE/'candidate-full.o'
assert allocated(ElfImage(original_object))==a
def undefined(p):return sorted(subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(p)],text=True).splitlines())
assert undefined(W/'control-full.o')==undefined(W/'candidate-full.o')
control=ElfImage(W/'control.elf');candidate=ElfImage(W/'candidate.elf')
assert control.bytes_at(control.named_sections['.rodata'])==candidate.bytes_at(candidate.named_sections['.rodata'])
assert candidate.named_sections['.rodata'][5]==780
commands=[];contexts=[]
for label,cpu,use,hard in [('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)]:
 images=[]
 for variant,source in [('control',BASE/'native_eabi_m0.cpp'),('candidate',W/'native_eabi_m0.cpp')]:
  cmd=[str(CC/'arm-none-eabi-g++'),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),'-Os','-std=gnu++17','-fno-exceptions','-fno-rtti','-fno-unwind-tables','-fno-use-cxa-atexit','-ffunction-sections','-fdata-sections','-fno-lto','-I',str(P/'source/code')]
  if use:cmd+=['-DMK61_USE_M0_EABI=1']
  if hard:cmd+=['-mfpu=fpv4-sp-d16']
  out=W/(label+'-'+variant+'.o');cmd+=['-c',str(source),'-o',str(out)]
  subprocess.run(cmd,check=True);commands.append(cmd);images.append(ElfImage(out))
 assert allocated(images[0])==allocated(images[1]),label
 contexts.append(dict(context=label,allocated_code_and_data_identical=True,allocated_bytes=sum(map(len,allocated(images[1]).values()))))
bindings=json.loads((W/'candidate-build.json').read_text())['resident_bindings']
parentbindings=json.loads((W/'control-build.json').read_text())['resident_bindings'];assert bindings==parentbindings
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
assert all(resident.symbols[n]==v for n,v in bindings.items())
report=dict(status='PASS_ONLY_RP2040_ATAN_REPAIR_GEOMETRY_GATE_CHANGED',
            parent_rebuilt_all_allocated_sections_equal_accepted_atan_object=True,parent_allocated_bytes=sum(map(len,a.values())),
            added_sections={n:len(b[n]) for n in added},changed_sections={n:[len(a[n]),len(b[n])] for n in changed},
            total_allocated_bytes_delta=sum(map(len,b.values()))-sum(map(len,a.values())),other_allocated_sections_and_all_tables_identical=True,
            entire_object_undefined_dependencies_unchanged=True,fixture_RO_atan_table_bytes=780,fixture_RO_atan_table_identical=True,
            resident_binding_maps_identical_and_pinned=True,new_tables_or_global_RAM_or_libgcc_dependency=False,contexts=contexts,
            source_sha256=sha(W/'native_eabi_m0_atan_fast.inc'),candidate_full_object_sha256=sha(W/'candidate-full.o'),
            candidate_ELF_sha256=sha(W/'candidate.elf'),control_ELF_sha256=sha(W/'control.elf'),accepted_parent_object_sha256=sha(original_object),
            commands=commands,scope='Public full objects and local atan component; resident helpers/ROM are pinned. No production relink or whole M4 rebuild.',
            canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'isolation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
