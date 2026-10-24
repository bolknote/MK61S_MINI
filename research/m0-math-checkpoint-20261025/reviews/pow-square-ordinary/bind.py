"""Independent source/pin/symbol/section binding and exact rebuilds."""
from pathlib import Path
import ast,difflib,hashlib,json,re,shlex,struct,subprocess,sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');P=R/'.build/m0-pow-square-ordinary-20261024';V=R/'.build/m0-asin-scaled-bound-v164-20261023';B=R/'.build/m0-exp-cached-product-20261024';T=R/'.build/m0-pow-square-exact-20261024';O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),bytes=Path(p).stat().st_size,sha256=sha(p))
assert sha(P/'FROZEN.json')=='f1d64d6955b8a9b96af272a6191196a39709c6896617f8557d555a78e35e478e'
assert sha(P/'result.json')=='4a68d9a4e8fbbb9c253079eb6621fe2357c19088fcfa1ee4cb70864483e93ca2'
parent_receipt=R/'.build/m0-exp-cached-product-independent-20261024/FINAL-REVIEW.json'
assert sha(parent_receipt)=='857e13f2131b03257a493de620a250092ee383af7045271bc06ac865f73068f3'
verified=[]
for name,base,count in [('FROZEN.json',P,102),('source-lineage-pins.json',R,105)]:
 d=read(P/name)['files'];assert len(d)==count
 for n,x in d.items():assert sha(base/n)==x['sha256'] and (base/n).stat().st_size==x['bytes'];verified.append(ref(base/n))
for n,s in read(P/'qualification.json')['corpus_pins'].items():assert sha(R/n)==s
assert (P/'control/native_eabi_m0.cpp').read_bytes()==(B/'candidate/native_eabi_m0.cpp').read_bytes()
assert (P/'control/native_eabi_m0.S').read_bytes()==(V/'source/code/native_eabi_m0.S').read_bytes()
for label in ['control','candidate','whole-fixture']:
 assert (P/label/'native_eabi_m0_pow_exp_product.inc').read_bytes()==(B/'candidate/native_eabi_m0_pow_exp_product.inc').read_bytes()
patch=''
for base,new,n in [(P/'control/native_eabi_m0.cpp',P/'candidate/native_eabi_m0.cpp','native_eabi_m0.cpp'),(P/'control/native_eabi_m0.S',P/'candidate/native_eabi_m0.S','native_eabi_m0.S')]:
 patch+=''.join(difflib.unified_diff(base.read_text().splitlines(True),new.read_text().splitlines(True),fromfile='a/code/'+n,tofile='b/code/'+n))
for n in ['native_eabi_m0_pow_ordinary.inc','native_eabi_m0_pow_square.inc']:
 patch+=''.join(difflib.unified_diff([], (P/'candidate'/n).read_text().splitlines(True),fromfile='/dev/null',tofile='b/code/'+n))
assert patch==(P/'accepted-exp-product-to-pow.patch').read_text()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def body(e,n):
 # ET_REL sections share VMA0: use st_shndx, never the first address match.
 for tab in e.sections:
  if tab[1]!=2:continue
  strings=e.bytes_at(e.sections[tab[6]])
  for off in range(0,tab[5],tab[9]):
   name,a,z,info,other,index=struct.unpack_from('<IIIBBH',e.bytes_at(tab),off)
   if e.string(strings,name)!=n:continue
   a&=~1;s=e.sections[index];assert s[2]&2 and s[3]<=a<a+z<=s[3]+s[5]
   return e.bytes_at(s)[a-s[3]:a-s[3]+z]
 raise KeyError(n)
# Semantic relocation comparison reused as an explicitly extracted pure
# parser, without executing the previous review's top-level build script.
tree=ast.parse((R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text())
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(O/'bind.py'),'exec'),globals())
def realrels(e):return {k:v for k,v in relocs(e).items() if not k.startswith('.debug')}
cpp0,cpp1=ElfImage(P/'control-full.o'),ElfImage(P/'candidate-full.o');c0,c1=allocated(cpp0),allocated(cpp1)
assert c0==allocated(ElfImage(B/'candidate-full.o'))
assert c1.keys()-c0.keys()=={'.m0_pow_dispatch_ordinary'} and all(c0[n]==c1[n] for n in c0)
rc0,rc1=realrels(cpp0),realrels(cpp1)
assert all(rc0[n]==rc1[n] for n in rc0)
assert len(c1['.m0_pow_dispatch_ordinary'])==272
aliases=read(P/'build.json')['storage_free_alias_targets']
for alias,target in aliases.items():assert cpp1.symbols[alias]==cpp1.symbols[target] and cpp1.sizes[alias]==cpp1.sizes[target]
as0,as1=ElfImage(P/'control-full-asm.o'),ElfImage(P/'candidate-full-asm.o');a0,a1=allocated(as0),allocated(as1)
assert a0.keys()==a1.keys() and {n for n in a0 if a0[n]!=a1[n]}=={'.m0_pow_dispatch_extension'}
assert len(a1['.m0_pow_dispatch_extension'])-len(a0['.m0_pow_dispatch_extension'])==320
ar0,ar1=realrels(as0),realrels(as1)
assert {k for k in ar0.keys()|ar1.keys() if ar0.get(k)!=ar1.get(k)}=={'.m0_pow_dispatch_extension'}
for context in ['generic_M0','M4_soft','M4_hard']:
 for kind in ['cpp','asm']:
  e0,e1=ElfImage(P/(context+'-control-'+kind+'.o')),ElfImage(P/(context+'-candidate-'+kind+'.o'))
  assert allocated(e0)==allocated(e1) and realrels(e0)==realrels(e1)
  if context.startswith('M4'):assert sum(map(len,allocated(e1).values()))==0
partial,whole=ElfImage(P/'candidate.elf'),ElfImage(P/'whole-source.elf')
assert allocated(partial)==allocated(whole)
module=partial.bytes_at(partial.named_sections['.square']);name='mk61_m0_pow_square_exact'
assert len(module)==328 and hashlib.sha256(module).hexdigest()=='776eec5cec3fa39bff045d8be18e4fd1e33dba22ae0ce195db790a218a78c0ba'
for e in [whole,as1,ElfImage(T/'unit.elf'),ElfImage(T/'candidate.elf')]:assert body(e,name)==module
assert body(ElfImage(P/'control.elf'),'mk61_m0_pow_fast')==body(ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf'),'mk61_m0_pow_fast')
assert (P/'square.S').read_text().replace('.m0_pow_square_exact_only','.m0_pow_dispatch_extension')==(P/'candidate/native_eabi_m0_pow_square.inc').read_text()
db=read(V/'build/compile_commands.json');build=read(P/'build.json');iso=read(P/'isolation.json');cc=Path(build['commands'][0][0]).parent
for n in ['cpp','S']:
 entry=next(d for d in db if d['file'].endswith('/code/native_eabi_m0.'+n));flags=shlex.split(entry['command'])
 for i,label in enumerate(['control','candidate']):
  cmd=build['commands'][i] if n=='cpp' else iso['commands'][i]
  expected=list(flags);expected[expected.index(entry['file'])]=str(P/label/('native_eabi_m0.'+n));expected[expected.index('-o')+1]=str(P/(label+('-full.o' if n=='cpp' else '-full-asm.o')))
  assert cmd==expected
undef=lambda p:subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(p)],text=True).splitlines()
assert undef(P/'control-full.o')==undef(P/'candidate-full.o')
assert not undef(P/'candidate.elf') and not undef(P/'whole-source.elf')
out=O/'rebuild';out.mkdir(exist_ok=True);commands=[];matched=[];remap={}
if '--reuse-own-rebuild' in sys.argv:
 old=read(O/'binding.json');commands=old['commands'];matched=old['matched']
 for x in matched:assert sha(Path(x['path']))==x['sha256']==sha(P/Path(x['path']).name)
else:
 for c in build['commands']+iso['commands'][:4]:
  cmd=[remap.get(x,x) for x in c];i=cmd.index('-o')+1;original=c[i];target=out/Path(original).name;cmd[i]=str(target)
  assert not any(x in ['-MD','-MMD','-MF'] for x in cmd)
  p=subprocess.run(cmd,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  commands.append(dict(argv=cmd,returncode=p.returncode,stdout=p.stdout));assert p.returncode==0,commands[-1]
  assert sha(target)==sha(Path(original)),str(target)
  matched.append(ref(target));remap[original]=str(target)
# Own standalone unit is assembled from the actual intended include. Only
# its section name changes; -Wa,-L exposes local audit labels, not code.
unit_source=(P/'candidate/native_eabi_m0_pow_square.inc').read_text().replace('.m0_pow_dispatch_extension','.audit_square')
(O/'square-audit.S').write_text(unit_source)
(O/'unit.ld').write_text('PHDRS { square PT_LOAD FLAGS(5); } SECTIONS { .square 0x10000000 : { *(.audit_square) } :square /DISCARD/ : { *(.ARM*) *(.comment) *(.note*) } }\n')
unitcmd=[[str(cc/'arm-none-eabi-gcc'),'-mcpu=cortex-m0plus','-mthumb','-DMK61_USE_M0_EABI=1','-DMK61_M0_RP2040_EABI=1','-Wa,-L','-c',str(O/'square-audit.S'),'-o',str(O/'square-audit.o')],[str(cc/'arm-none-eabi-ld'),'-e',name,'-T',str(O/'unit.ld'),str(O/'square-audit.o'),'-o',str(O/'unit.elf')]]
for cmd in unitcmd:
 p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);assert p.returncode==0,p.stdout
ue=ElfImage(O/'unit.elf');assert body(ue,name)==module and not undef(O/'unit.elf')
assert set(allocated(ue))=={'.square'} and not ue.named_sections['.square'][2]&1
dis=subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d',str(O/'unit.elf')],text=True);(O/'square.dis').write_text(dis)
assert sum(bool(re.search(r'\s+muls\s',x)) for x in dis.splitlines())==10
d=dict(status='PASS_INDEPENDENT_POW_SOURCE_PINS_REBUILDS_AND_NUMERIC_MODULE_BINDING',accepted_parent=ref(parent_receipt),frozen_artifacts=102,lineage_pins=105,corpus_pins=12,verified=verified,patch_exact=True,old_CPP_allocated_and_semantic_relocations_equal=True,new_CPP_section_bytes=272,only_ASM_section_changed='.m0_pow_dispatch_extension',ASM_object_delta=320,combined_object_delta=592,private_overlay_delta=608,all_aliases_storage_free=True,generic_M0_M4_selected_TUs_byte_equal=True,whole_M4_not_built=True,private_not_bootable_firmware=True,whole_intended_source_and_tested_partial_ELF_allocated_equal=True,square_body_same_across_current_intended_trial_inheritedunit_ownunit=True,square_bytes=328,square_module_SHA256=hashlib.sha256(module).hexdigest(),unit=ref(O/'unit.elf'),product_audit_address=ue.symbols['.Lsquare_choose_word'],square_entry=ue.symbols[name],rebuilds=12,matched=matched,commands=commands,own_unit_commands=unitcmd,hardware=False,canonical=False)
(O/'binding.json').write_text(json.dumps(d,indent=2)+'\n');print(json.dumps({k:v for k,v in d.items() if k not in ['commands','verified','matched','own_unit_commands']},indent=2))
