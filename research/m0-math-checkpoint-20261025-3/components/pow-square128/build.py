"""Compile full RP source controls and isolate its unchanged-size square slot."""
from pathlib import Path
import ast,difflib,hashlib,json,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
assert not (W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text()
start=source.index('\t.section\t.m0_pow_square_fixed,')
end=source.index('\t.section\t.m0_pow_root_prefix,',start+1)
intended=source[:start]+(W/'square128.S.inc').read_text()+'\n'+source[end:]
(W/'candidate/native_eabi_m0_pow_root_prefix.inc').write_text(intended)
(W/'square128-only.patch').write_text(''.join(difflib.unified_diff(source.splitlines(True),intended.splitlines(True),fromfile='a/code/native_eabi_m0_pow_root_prefix.inc',tofile='b/code/native_eabi_m0_pow_root_prefix.inc')))
entry=next(r for r in json.loads((P/'build/compile_commands.json').read_text()) if r['file'].endswith('/code/native_eabi_m0_rp2040.S'))
flags=shlex.split(entry['command']);tc=Path(flags[0]).parent;commands=[];images={}
tree=ast.parse((ROOT/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),__file__,'exec'),globals())
alloc=lambda e:{n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8 and s[5]}
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  cmd=list(flags)
  if context!='RP':cmd=[s for s in cmd if s!='-DMK61_M0_RP2040_EABI=1']
  if context.startswith('M4'):
   cmd[cmd.index('-mcpu=cortex-m0plus')]='-mcpu=cortex-m4'
   cmd[cmd.index('-DMK61_USE_M0_EABI=1')]='-DMK61_USE_M0_EABI=0'
   if context=='M4_hard':cmd+=['-mfloat-abi=hard','-mfpu=fpv4-sp-d16']
  cmd[cmd.index(entry['file'])]=str(W/label/'native_eabi_m0_rp2040.S')
  cmd[cmd.index('-o')+1]=str(W/(context+'-'+label+'.o'))
  subprocess.run(cmd,cwd=W,check=True);commands.append(cmd);images[context,label]=ElfImage(W/(context+'-'+label+'.o'))
 a,b=[images[context,label] for label in ['control','candidate']]
 if context!='RP':assert alloc(a)==alloc(b) and relocs(a)==relocs(b)
a,b=[images['RP',label] for label in ['control','candidate']]
aa,bb=alloc(a),alloc(b)
assert aa.keys()==bb.keys() and {n for n in aa if aa[n]!=bb[n]}=={'.m0_pow_square_fixed'}
assert len(aa['.m0_pow_square_fixed'])==len(bb['.m0_pow_square_fixed'])==310
for name,v in relocs(a).items():
 if name in aa and name!='.m0_pow_square_fixed':assert v==relocs(b)[name],name
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
address=resident.symbols['pow_integer128_square']&~1
script='pow_integer128_approx_high64 = '+hex(resident.symbols['pow_integer128_approx_high64'])+';\n'
script+='PHDRS { code PT_LOAD FLAGS(5); }\nSECTIONS { .square '+hex(address)+' : { KEEP(*(.m0_pow_square_fixed)) } :code\n /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) *(.ARM.attributes) } }\n'
(W/'square.ld').write_text(script)
meta={}
for label in ['control','candidate']:
 cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','pow_integer128_square','-T',str(W/'square.ld'),str(W/('RP-'+label+'.o')),'-o',str(W/(label+'.elf'))]
 subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
 im=ElfImage(W/(label+'.elf'));assert im.named_sections['.square'][5]==310
 if label=='control':
  s=next(s for s in resident.named_sections.values() if s[3]<=address<s[3]+s[5])
  assert im.bytes_at(im.named_sections['.square'])==resident.bytes_at(s)[address-s[3]:address-s[3]+310]
 with (W/(label+'.dis')).open('w') as f:subprocess.run([str(tc/'arm-none-eabi-objdump'),'-dr',str(W/(label+'.elf'))],stdout=f,check=True)
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),function_bytes=im.sizes['pow_integer128_square'],slot_bytes=310)
out=dict(status='BUILT_PRIVATE_SQUARE128_NOT_QUALIFIED',images=meta,entry_address=address,
 only_changed_allocated_section='.m0_pow_square_fixed',allocated_section_size_unchanged=True,
 all_other_RP_bytes_and_relocations_equal=True,default_M0_M4_soft_hard_selected_assembly_equal=True,
 commands=commands,hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k!='commands'},indent=2))
