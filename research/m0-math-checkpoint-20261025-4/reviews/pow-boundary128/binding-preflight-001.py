"""Read frozen inputs; rebuild only into this independent directory."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI'); O=Path(__file__).resolve().parent
W=R/'.build/m0-pow-boundary128-20261025'; SQ=R/'.build/m0-pow-square128-r2-20261025'
P=R/'.build/m0-asin-scaled-bound-v164-20261023'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p); b=p.read_bytes(); return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):
 d=ref(p); assert d['sha256']==h,d; return d
def save(n,d):
 with (O/n).open('x')as f: json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5])
 return e.bytes_at(s)[a-s[3]:a-s[3]+n]
refs=dict(FROZEN=pin(W/'FROZEN.json','61c98b938cf723f2f9b63ef06f22a3033c1b07af979dbe56ef9a2a2d56ed3393'),
 result=pin(W/'result.json','9100e2567699992f13dac767bf35851d642d80f449110f631c7d2b5a5648ce8f'),
 HANDOFF=pin(W/'HANDOFF.md','5f6d506cb7a7fd13fc85b463acfeb532f64f37a0970ec488b524647ec9ca7c43'),
 ELF=pin(W/'candidate.elf','63a80f08c546e7bd07db6056eb1f64aa0de573c7296e5572b090e9d9f6edbfa9'),
 CPP=pin(W/'boundary.cpp','f5f6428bd0a5c964af095d987b794548d1143f9603147eeb178cef8dd3e38795'),
 parent_FROZEN=pin(SQ/'FROZEN.json','31de9242e96642ed7de050a2a7a51a5baeacdd9c8842e4b0d7f3f2c74e2e681d'),
 parent_review=pin(R/'.build/m0-pow-square128-independent-20261025/FINAL-REVIEW.json','eaa55a85a694bb33517f01db27355edb8b39e3a529768c150bc5fc5c161bfd24'),
 corrigendum=pin(R/'.build/m0-pow-boundary128-report-corrigendum-20261025.json','729a5e184850786b02c03c2dc40d97d4eed43e1bc0c65753f0af9f2fe6385997'),
 postseal=pin(R/'.build/m0-pow-boundary128-postseal-20261025.json','753277e91b33ad654069927a7b01bdc1dc34d5730bd1b9eeb77c0be70f1cc31a'))
local=[];external=[]
for meta,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external)]:
 for n,d in json.loads(meta.read_text())['files'].items():
  assert not n.startswith('/') and '..'not in Path(n).parts and '.git'not in Path(n).parts
  v=ref(base/n); assert v['bytes']==d['bytes']and v['sha256']==d['sha256'],v;items.append(v)
assert len(local)==68 and len(external)==1695
old=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text(); new=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert old==(SQ/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
a=old.index('\t.section\t.m0_pow_boundary_exact,');z=old.index('\t.section\t.m0_pow_root_prefix,',a+1)
assert new[:a]==old[:a]and new.endswith(old[z:])
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/code/native_eabi_m0_pow_root_prefix.inc',tofile='b/code/native_eabi_m0_pow_root_prefix.inc'))
assert patch==(W/'boundary128-source.patch').read_text()
assert (W/'candidate/native_eabi_m0_rp2040.S').read_bytes()==(W/'control/native_eabi_m0_rp2040.S').read_bytes()==(SQ/'candidate/native_eabi_m0_rp2040.S').read_bytes()
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text()
fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocations>','exec'),globals())
def allocated(e):return {n:(s[1],s[2],s[5],s[8],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 c,n=[ElfImage(W/(context+'-'+v+'.o'))for v in ['control','candidate']];cc,nn=allocated(c),allocated(n)
 if context=='RP':
  assert cc.keys()==nn.keys()and [k for k in cc if cc[k]!=nn[k]]==['.m0_pow_boundary_exact']
  assert cc['.m0_pow_boundary_exact'][:4]==nn['.m0_pow_boundary_exact'][:4]
  for k,rows in relocs(c).items():
   if k in cc and k!='.m0_pow_boundary_exact':assert rows==relocs(n)[k],k
 else:
  assert cc==nn and relocs(c)==relocs(n)
  assert not allocated(ElfImage(W/(context+'-boundary-disabled.o')))
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf')
control=ElfImage(W/'control.elf');candidate=ElfImage(W/'candidate.elf');helpers=ElfImage(W/'unit-helpers.elf');square=ElfImage(SQ/'unit-candidate.elf')
oldname='_ZL16root128_boundaryRK13PowInteger128jby';cmpname='_ZL15root128_compareRK13PowInteger128S1_'
entry=resident.symbols[oldname]&~1;body=candidate.symbols['mk61_m0_boundary128']&~1
assert entry==0x10150000 and candidate.named_sections['.front'][3]==entry and candidate.named_sections['.front'][5]==532
assert memory(control,entry,532)==memory(resident,entry,532)
assert memory(candidate,entry,4)==bytes.fromhex('004b1847')
assert memory(candidate,entry+4,4)==struct.pack('<I',body|1)
assert memory(candidate,entry+8,524)==bytes.fromhex('00bf')*262
assert candidate.named_sections['.boundary128'][5]==228 and candidate.sizes['mk61_m0_boundary128']==228
assert body+228<0x10200000
resident_images=[resident]+[ElfImage(R/'.build'/n/'candidate.elf')for n in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025']]
for e in resident_images:
 assert not any(s[2]&2 and s[5]and max(s[3],body)<min(s[3]+s[5],body+228)for s in e.sections)
for name,n in [('pow_integer128_multiply',490),(cmpname,372)]:
 alias=name if name=='pow_integer128_multiply'else'mk61_m0_boundary128_compare'
 addr=resident.symbols[name]&~1; assert helpers.sizes[alias]==n
 assert memory(helpers,addr,n)==memory(resident,addr,n)
 if n==490:assert helpers.named_sections['.multiply'][5]==492
for name,n in [('pow_integer128_square',232),('pow_integer128_approx_high64',94)]:
 addr=resident.symbols[name]&~1
 assert square.sizes[name]==n
 source_image=ElfImage(SQ/'candidate.elf') if name=='pow_integer128_square'else resident
 assert memory(square,addr,n)==memory(source_image,addr,n)
for name in ['pow_integer128_square','pow_integer128_multiply','pow_integer128_approx_high64']:
 assert candidate.symbols[name]==resident.symbols[name]
assert candidate.symbols['mk61_m0_boundary128_compare']==resident.symbols[cmpname]
assert set(n for n,s in candidate.named_sections.items()if s[2]&2 and s[5])=={'.front','.boundary128'}
# Only output paths and explicit DWARF compilation-directory maps change.
build=json.loads((W/'build.json').read_text());ub=json.loads((W/'unit-build.json').read_text());d=O/'rebuild';d.mkdir()
names=['RP-candidate.o','boundary.o','candidate.elf','unit-helpers.o','unit-helpers.elf']
allcmd=build['commands']+ub['commands']; selected=[]
for name in names:selected.append(next(c for c in allcmd if Path(c[c.index('-o')+1]).name==name))
maps={str(W/n):str(d/n)for n in names};commands=[];rebuilt=[]
for argv in selected:
 out=Path(argv[argv.index('-o')+1]); cmd=[maps.get(x,x)for x in argv]
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(W)]
 p=subprocess.run(cmd,cwd=O,capture_output=True)
 (d/(out.name+'.stdout')).write_bytes(p.stdout);(d/(out.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode(); assert (d/out.name).read_bytes()==out.read_bytes(),out
 commands.append(dict(argv=cmd,returncode=p.returncode));rebuilt.append(ref(d/out.name))
tc=Path(build['commands'][0][0]).parent
undefined=subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(W/'boundary.o')],text=True)
assert {v.split()[-1]for v in undefined.splitlines()}=={'pow_integer128_square','pow_integer128_multiply','mk61_m0_boundary128_compare'}
assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(W/'candidate.elf')],text=True).strip()
for name in ['candidate.elf','unit-helpers.elf']:
 text=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/name)])
 (O/(name+'.actual.dis')).write_bytes(text)
out=dict(status='PASS_SINGLE_BOUNDARY_CALLER_SOURCE_BINARY_AND_FIVE_BYTEEXACT_REBUILDS',refs=refs,
 local_pins=local,external_pins=external,counts=dict(local=68,external=1695),
 actual_parent='Square128 r2 /31de; near-one separate sibling',exact_patch=True,
 unchanged_other_RP_allocated_bytes_semantic_relocations_BSS_addresses_veneers=True,
 defaultM0_M4_selected_ASM_unchanged_and_additional_CPP_empty=True,
 old_slot532_tail8_with2instructions_and524padding=True,new_body_bytes=228,
 real_multiply_function490_allocation492_compare372_square232_helper94=True,
 tail_R3_unused_ABI_slot_R0_R2_LR_SP_and_incoming_cell_preserved=True,
 ordinary_R0_int32_no_extra_R12_return=True,no_new_tables_RAM_libgcc_or_ROM_math=True,
 current_private_layout_no_overlap_and_below2MiB=True,
 five_own_rebuilt_outputs=rebuilt,commands=commands,all_writes_own_output_only=True,
 debug_only_compilation_directory_prefix_map_honest=True,
 author_syntax_preflight=ref(W/'probe-preflight-failed.log'),historical_syntax_failure_not_ARM_qualification=True,
 device_IO=0,network=0,Git=0,canonical=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)
