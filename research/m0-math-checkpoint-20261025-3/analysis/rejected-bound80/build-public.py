"""One old-entry tail veneer, relocated old fallback, real whole RP source build."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
original_name='_ZL16root128_boundaryRK13PowInteger128jby'
compare_name='_ZL15root128_compareRK13PowInteger128S1_'
newcompare='mk61_m0_bound80_old_compare'
source=(BASE/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
start=source.index('\t.section\t.m0_pow_boundary_exact,')
end=source.index('\t.section\t.m0_pow_root_prefix,',start+1)
block=source[start:end]
fallback=block.replace('.m0_pow_boundary_exact','.m0_pow_bound80_fallback').replace(original_name,'mk61_m0_bound80_old_boundary').replace(compare_name,newcompare)
fallback=fallback.replace('\t.type\tmk61_m0_bound80_old_boundary', '\t.global mk61_m0_bound80_old_boundary\n\t.type\tmk61_m0_bound80_old_boundary')
stub='''.section .m0_pow_boundary_exact,"ax",%progbits
.p2align 2
.type OLD_NAME,%function
.thumb_func
OLD_NAME:
 .fnstart
 ldr r3,.Lbound80_front_target
 bx r3
.p2align 2
.Lbound80_front_target: .word mk61_m0_bound80_filter
.size OLD_NAME,.-OLD_NAME
.cantunwind
.fnend
.fill (532-(.-OLD_NAME))/2,2,0xbf00
'''.replace('OLD_NAME',original_name)
changed=source[:start]+stub+'\n'+fallback+'\n'+source[end:]
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 (d/'native_eabi_m0_rp2040.S').write_bytes((BASE/'candidate/native_eabi_m0_rp2040.S').read_bytes())
 (d/'native_eabi_m0_pow_root_prefix.inc').write_text(source if label=='control' else changed)
(W/'boundary80-source.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),changed.splitlines(True),fromfile='a/code/native_eabi_m0_pow_root_prefix.inc',tofile='b/code/native_eabi_m0_pow_root_prefix.inc')))
(W/'control-slot.S').write_text('.syntax unified\n.cpu cortex-m0plus\n.thumb\n.global '+original_name+'\n'+block.replace(compare_name,newcompare))
entry=next(e for e in json.loads((P/'build/compile_commands.json').read_bytes()) if e['file'].endswith('/code/native_eabi_m0_rp2040.S'))
flags=shlex.split(entry['command']);tc=Path(flags[0]).parent;commands=[];images={}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),__file__,'exec'),globals())
def allocated(e):return {n:(s[1],s[2],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  cmd=list(flags)
  if context!='RP':cmd=[s for s in cmd if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   cmd[cmd.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4';cmd[cmd.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':cmd+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  cmd[cmd.index(entry['file'])]=str(W/label/'native_eabi_m0_rp2040.S');cmd[cmd.index('-o')+1]=str(W/(context+'-'+label+'.o'))
  subprocess.run(cmd,cwd=W,check=True);commands.append(cmd);images[context,label]=ElfImage(W/(context+'-'+label+'.o'))
 a,b=[images[context,label]for label in ['control','candidate']]
 aa,bb=allocated(a),allocated(b)
 if context=='RP':
  assert set(bb)-set(aa)=={'.m0_pow_bound80_fallback','.ARM.exidx.m0_pow_bound80_fallback'}
  assert bb['.ARM.exidx.m0_pow_bound80_fallback'][2]==8
  assert {n for n in aa if aa[n]!=bb[n]}=={'.m0_pow_boundary_exact'}
  assert aa['.m0_pow_boundary_exact'][:3]==bb['.m0_pow_boundary_exact'][:3]
  for n,rs in relocs(a).items():
   if n in aa and n!='.m0_pow_boundary_exact':assert rs==relocs(b)[n],n
 else:assert aa==bb and relocs(a)==relocs(b)
cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-c',str(W/'control-slot.S'),'-o',str(W/'control-slot.o')]
subprocess.run(cmd,check=True);commands.append(cmd)
e=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');old=e.symbols[original_name]&~1
defs={'pow_integer128_approx_high64':e.symbols['pow_integer128_approx_high64'],
      'pow_integer128_multiply':e.symbols['pow_integer128_multiply'],newcompare:e.symbols[compare_name]}
assignments=''.join(n+' = '+hex(v)+';\n'for n,v in defs.items())
scripts={
 'control':assignments+'''PHDRS { front PT_LOAD FLAGS(5); }
SECTIONS { .front OLD_ADDRESS : { KEEP(*(.m0_pow_boundary_exact)) } :front
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
''',
 'candidate':assignments+'''PHDRS { front PT_LOAD FLAGS(5); code PT_LOAD FLAGS(5); }
SECTIONS { .front OLD_ADDRESS : { KEEP(*(.m0_pow_boundary_exact)) } :front
.bound80 0x101e0000 : { KEEP(*(.m0_pow_bound80_square)) KEEP(*(.m0_pow_bound80_wide32))
KEEP(*(.m0_pow_bound80_multiply)) KEEP(*(.m0_pow_bound80_compare)) KEEP(*(.m0_pow_bound80_filter)) *(.rodata*) } :code
.fallback ALIGN(4) : { KEEP(*(.m0_pow_bound80_fallback)) } :code
/DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }
'''}
meta={}
for label in ['control','candidate']:
 (W/(label+'.ld')).write_text(scripts[label].replace('OLD_ADDRESS',hex(old)))
 objects=[W/'control-slot.o']if label=='control'else[W/'RP-candidate.o',W/'kernels.o',W/'filter.o']
 cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e',original_name if label=='control'else'mk61_m0_bound80_filter','-T',str(W/(label+'.ld')),*map(str,objects),'-o',str(W/(label+'.elf'))]
 subprocess.run(cmd,check=True);commands.append(cmd)
 im=ElfImage(W/(label+'.elf'));s=im.named_sections['.front'];assert s[3]==old and s[5]==532
 if label=='control':
  resident=next(s for s in e.named_sections.values()if s[3]<=old and old+532<=s[3]+s[5])
  assert im.bytes_at(im.named_sections['.front'])==e.bytes_at(resident)[old-resident[3]:old-resident[3]+532]
 with (W/(label+'.dis')).open('w')as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-d',str(W/(label+'.elf'))],stdout=f,check=True)
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),allocated={n:dict(address=s[3],bytes=s[5])for n,s in im.named_sections.items()if s[2]&2 and s[5]})
out=dict(status='EXPERIMENTAL_CONSERVATIVE_BOUNDARY80_PUBLIC_IMAGES_NOT_QUALIFIED',images=meta,commands=commands,
 source_parent=str(BASE.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(BASE/'FROZEN.json'),
 M0_M4_selected_RP_source_controls_equal=True,all_other_RP_allocated_sections_bytes_relocations_unchanged=True,
 old_control_entry532bytes_exact_resident=True,hardware_accessed=False)
(W/'public-build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
