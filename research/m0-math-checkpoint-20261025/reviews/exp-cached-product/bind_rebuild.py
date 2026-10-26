"""Independent immutable-packet, source scope, ELF and rebuild checks."""
from pathlib import Path
import difflib, hashlib, json, shlex, struct, subprocess, sys
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI')
P=R/'.build/m0-exp-cached-product-20261024'
V=R/'.build/m0-asin-scaled-bound-v164-20261023'
O=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(p),sha256=sha(p),bytes=Path(p).stat().st_size)
assert sha(P/'FROZEN.json')=='765df6f87358d53a2d10d3b4c673fe8e4e85771c56e7d39b79bfe9df2ce5381c'
assert sha(P/'result.json')=='1e7123188b0cb84380acc840486e21993c3ad9b4ca2922443091a3c259a73288'
verified=[]
for anchor,base in [(P/'FROZEN.json',P),(P/'source-lineage-pins.json',R)]:
 for name,d in read(anchor)['files'].items():
  p=base/name;assert sha(p)==d['sha256'] and p.stat().st_size==d['bytes'],str(p)
  verified.append(ref(p))
assert len(read(P/'FROZEN.json')['files'])==91
assert len(read(P/'source-lineage-pins.json')['files'])==68
assert (P/'control/native_eabi_m0.cpp').read_bytes()==(V/'source/code/native_eabi_m0.cpp').read_bytes()
assert (P/'candidate/native_eabi_m0_pow_exp_product.inc').read_text().replace('.scratch_y.m0_pow_hot','.scratch_y.m0_exp_product_only')==(P/'cached-product.S').read_text()
patch=''.join(difflib.unified_diff((P/'control/native_eabi_m0.cpp').read_text().splitlines(True),(P/'candidate/native_eabi_m0.cpp').read_text().splitlines(True),fromfile='a/code/native_eabi_m0.cpp',tofile='b/code/native_eabi_m0.cpp'))
patch+=''.join(difflib.unified_diff((V/'source/code/native_eabi_m0_pow_exp_product.inc').read_text().splitlines(True),(P/'candidate/native_eabi_m0_pow_exp_product.inc').read_text().splitlines(True),fromfile='a/code/native_eabi_m0_pow_exp_product.inc',tofile='b/code/native_eabi_m0_pow_exp_product.inc'))
assert patch==(P/'V164-exp-and-product.patch').read_text()
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
def body(e,name):
 a=e.symbols[name]&~1;z=e.sizes[name]
 s=next(s for s in e.sections if s[2]&2 and s[3]<=a<a+z<=s[3]+s[5])
 return e.bytes_at(s)[a-s[3]:a-s[3]+z]
old,new=ElfImage(P/'control-full.o'),ElfImage(P/'candidate-full.o')
aa,bb=allocated(old),allocated(new)
assert aa.keys()==bb.keys() and {n for n in aa if aa[n]!=bb[n]}=={'.m0_exp_core'}
assert body(old,'exp_refine')==body(new,'exp_refine')
# Relocation targets are compared by their semantic symbol names, not the
# symbol-table indices which source debug metadata may renumber.
def relocs(e):
 out={}
 for s in e.sections:
  if s[1]!=9:continue
  tab=e.sections[s[6]];strings=e.bytes_at(e.sections[tab[6]])
  syms=[]
  for off in range(0,tab[5],tab[9]):
   n,v,z,info,other,idx=struct.unpack_from('<IIIBBH',e.bytes_at(tab),off)
   name=e.string(strings,n)
   if not name and idx<len(e.sections):name='SECTION:'+next((n for n,x in e.named_sections.items() if x==e.sections[idx]),str(idx))
   syms.append(name)
  target=next(n for n,x in e.named_sections.items() if x==e.sections[s[7]])
  out[target]=[(off,info&255,syms[info>>8]) for off,info in struct.iter_unpack('<II',e.bytes_at(s))]
 return out
ra,rb=relocs(old),relocs(new)
assert {k for k in ra.keys()|rb.keys() if ra.get(k)!=rb.get(k)}=={'.m0_exp_core','.debug_info','.debug_line','.debug_rnglists','.debug_loclists'}
resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf')
ce,ue=ElfImage(P/'candidate.elf'),ElfImage(P/'unit.elf')
name='mk61_m0_pow_exp_product'
assert resident.symbols[name]==ce.symbols[name]==0x20038ee5
assert body(ce,name)==(P/'rounded-product.bin').read_bytes()==body(ue,'audit_product')
assert body(resident,name)==(P/'parent-rounded-product.bin').read_bytes()==body(ue,'audit_parent_product')
assert len(body(ce,name))==168 and len(body(resident,name))==182
wrapper=body(resident,'mk61_m0_pow_exp_product_flash')
assert len(wrapper)==16 and wrapper[-4:]==struct.pack('<I',ce.symbols[name])
assert len(wrapper)<len(body(ce,name)) and wrapper!=body(ce,name)
assert set(allocated(ue))=={'.text','.product','.parent_product'}
assert all(not (s[2]&1) for s in ue.sections if s[2]&2)
rn=next(n for n in ce.symbols if 'refine_exp_table' in n and ce.sizes.get(n)==6144)
urn=next(n for n in ue.symbols if 'refine_exp_table' in n and ue.sizes.get(n)==6144)
assert body(ce,rn)==body(ue,urn)
# Literal helper/pack bodies and the complete Q94 table in unit.cpp are
# source-bound; the stubs apply only when the real helper declines.
source=(P/'candidate/native_eabi_m0.cpp').read_text();unit=(P/'unit.cpp').read_text()
def block(start):
 a=source.index('{',start);d=0
 for z in range(a,len(source)):
  if source[z]=='{':d+=1
  elif source[z]=='}':
   d-=1
   if not d:return source[start:z+1]
tiny=block(source.index('__attribute__((always_inline)) inline U exp_tiny_rne('))
normal=block(source.index('  if(k>=-1022 && k<=1023) {',source.index('MK61_SOFT_PCS double mk61_m0_exp(')))
assert tiny in unit and normal in unit
for label in ['generic_M0','M4_soft','M4_hard']:
 a,b=ElfImage(P/(label+'-control.o')),ElfImage(P/(label+'-candidate.o'))
 assert allocated(a)==allocated(b)
 ar,br=relocs(a),relocs(b)
 assert {k:ar[k] for k in ar if not k.startswith('.debug')}=={k:br[k] for k in br if not k.startswith('.debug')}
 assert not any(allocated(ElfImage(P/(label+'-product.o'))).values())
build=read(P/'build.json');ub=read(P/'unit-build.json');cc=Path(build['commands'][0][0]).parent
entry=next(d for d in read(V/'build/compile_commands.json') if d['file'].endswith('/code/native_eabi_m0.cpp'))
original=shlex.split(entry['command'])
assert '-Os' in original and '-fno-lto' in original
for i,label in enumerate(['control','candidate']):
 expected=list(original);expected[expected.index(entry['file'])]=str(P/label/'native_eabi_m0.cpp');expected[expected.index('-o')+1]=str(P/(label+'-full.o'))
 assert build['commands'][i]==expected
assert allocated(ElfImage(Path(entry['output'])))==allocated(old)
for name,address in build['resident_bindings'].items():
 expected=resident.symbols['__wrap_'+name] if name in ('memcpy','memset') else resident.symbols[name]
 assert address==expected
 if name!='mk61_m0_pow_exp_product':assert ce.symbols[name]==expected
undefined=lambda p:subprocess.check_output([str(cc/'arm-none-eabi-nm'),'-u',str(p)],text=True).splitlines()
assert undefined(P/'control-full.o')==undefined(P/'candidate-full.o')
assert not undefined(P/'candidate.elf') and not undefined(P/'unit.elf')
dis=subprocess.check_output([str(cc/'arm-none-eabi-objdump'),'-d',str(P/'cached-product.o')],text=True)
instructions=[]
import re
for line in dis.splitlines():
 m=re.match(r'\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)',line)
 if m:instructions.append((int(m[1],16),m[2],m[3]))
assert len(instructions)==84 and all(len(x[1])==4 for x in instructions)
assert sum(x[2]=='muls' for x in instructions)==13
assert not any(x[2].startswith('b') for x in instructions)
(O/'product.dis').write_text(dis)
outdir=O/'rebuild';outdir.mkdir(exist_ok=True)
commands=[];matched=[]
reuse='--reuse-own-rebuild' in sys.argv
local_outputs={str(P/n):str(outdir/n) for n in ['control-full.o','candidate-full.o','cached-product.o','control.elf','candidate.elf','unit.o','product-unit.o','unit.elf','integration-product.o']}
for command in ([] if reuse else build['commands']+ub['commands']+[read(P/'integration-source-proof.json')['command']]):
 command=[local_outputs.get(x,x) for x in command]
 assert not any(x in ('-MD','-MMD','-MF') for x in command)
 p=subprocess.run(command,cwd=P,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 commands.append(dict(argv=command,returncode=p.returncode,stdout=p.stdout))
 assert p.returncode==0,commands[-1]
 n=Path(command[command.index('-o')+1]).name
 assert sha(outdir/n)==sha(P/n),(n,sha(outdir/n),sha(P/n))
 matched.append(ref(outdir/n))
if reuse:
 prior=read(O/'binding-rebuild.json');commands=prior['commands'];matched=prior['matched']
 for item in matched:
  q=Path(item['path']);assert sha(q)==item['sha256']==sha(P/q.name)
result=dict(status='PASS_INDEPENDENT_91_ARTIFACT_68_LINEAGE_SOURCE_SCOPE_AND_REBUILDS',frozen=ref(P/'FROZEN.json'),result=ref(P/'result.json'),verified_artifacts=91,verified_external_lineage=68,verified=verified,patch_exact=True,CPP_changed_allocated_sections={'.m0_exp_core':[len(aa['.m0_exp_core']),len(bb['.m0_exp_core'])]},all_other_allocated_and_semantic_relocations_unchanged=True,product_bytes=[182,168],product_address='0x20038ee4',original_flash_wrapper_bytes=16,wrapper_is_not_a_unit_body=True,bare_units_contain_actual_candidate_and_parent_RAM_bodies=True,unit_has_no_firmware_or_ROM=True,generic_M0_M4_selected_TUs_equal_and_product_excluded=True,M4_selected_TUs_allocated_bytes=0,whole_M4_not_built=True,source_to_public_overlay_and_unit_ELF_rebuilt_byte_exact=True,matched=matched,commands=commands,canonical_integration=False,hardware=False)
(O/'binding-rebuild.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('verified','commands','matched')},indent=2))
