"""Frozen reciprocal source/ELF binding; all compiler outputs stay here."""
import ast,difflib,hashlib,json,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-soft-20261025'
B=R/'.build/m0-pow-boundary128-20261025';V=R/'.build/m0-asin-scaled-bound-v164-20261023';S=R/'.build/m0-ddiv-soft-seed17-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):
 d=ref(p);assert d['sha256']==h,d;return d
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def body(e,n):return mem(e,e.symbols[n]&~1,e.sizes[n])
refs=dict(FROZEN=pin(W/'FROZEN.json','13dc7f8186d4678fac6b7a0da0b27e00dbb678316e292d320d3eefdd35dbba0c'),
 result=pin(W/'result.json','f8bbd45f9481b2273aeb86e92c03de75132e925f40bdf699ac31da13af74fe38'),
 HANDOFF=pin(W/'HANDOFF.md','307b7255d45f51e4a4f867975e41c8f864c1524330ed54e4b05f59bb150d1516'),
 ELF=pin(W/'candidate.elf','285307160c39afa066f18e2784ad7704931f53e84c51dfe4c74febb352f976ae'),
 parent_FROZEN=pin(B/'FROZEN.json','61c98b938cf723f2f9b63ef06f22a3033c1b07af979dbe56ef9a2a2d56ed3393'),
 parent_review=pin(R/'.build/m0-pow-boundary128-independent-20261025/FINAL-REVIEW.json','6c1a375bbc8a07a45d387f146347584527c74fc60b890263dc2e4d85f61d2c8b'),
 parent_ROOT=pin(R/'.build/m0-pow-boundary128-root-acceptance-20261025-001/RECEIPT.json','260cb67e4cfd136f73affc5de7486a10ee0e732d9fed2d13e086d9e4e90005f3'),
 postseal=pin(R/'.build/m0-pow-reciprocal-soft-postseal-20261025.json','5b10494fe10c9bcaf39b59185a3185e3a35d4021905626f6abde9903381c34db'))
local=[];external=[]
for meta,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external)]:
 for n,d in json.loads(meta.read_text())['files'].items():
  assert not n.startswith('/')and'..'not in Path(n).parts and'.git'not in Path(n).parts
  r=ref(base/n);assert r['bytes']==d['bytes']and r['sha256']==d['sha256'],r;items.append(r)
assert len(local)==81 and len(external)==1814
parent=(B/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text();new=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert parent.count('\tbl\t__aeabi_ddiv\n')==1
assert new==parent.replace('\tbl\t__aeabi_ddiv\n','\tbl\tmk61_m0_hint_ddiv\n')
assert new==(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text()
assert ''.join(difflib.unified_diff(parent.splitlines(True),new.splitlines(True),fromfile='parent/root-prefix.inc',tofile='candidate/root-prefix.inc'))==(W/'root-call.patch').read_text()
assert (W/'control/native_eabi_m0_rp2040.S').read_bytes()==(W/'candidate/native_eabi_m0_rp2040.S').read_bytes()==(B/'candidate/native_eabi_m0_rp2040.S').read_bytes()
bridge='''.Lrp2040_div_dirty_bridge:
 ldr r7,.Lrp2040_sw_target
 bx r7
.p2align 2
.Lrp2040_sw_target: .word mk61_m0_ddiv_sw_from_guard
.fill (12-(.-.Lrp2040_div_dirty_bridge))/2,2,0xbf00

'''
control=(W/'control-ddiv.S').read_text();candidate=(W/'candidate-ddiv.S').read_text();software=(W/'software.S').read_text();source=(V/'source/code/native_eabi_m0_rp2040.S').read_text()
assert candidate.count(bridge)==1 and candidate.replace(bridge,'').replace(' bcs .Lrp2040_div_dirty_bridge',' bcs .Lrp2040_div_slow')==control
# Normalize the clone in reverse, rather than execute the producer generator.
oldblock=source[source.index('.Lrp2040_small_divisor:'):source.index('#include',source.index('.Lrp2040_small_divisor:'))]
block=control[control.index('.Lrp2040_small_divisor:'):control.rindex('\n#endif\n')].rstrip('\n')+'\n'
block=block.replace('.global mk61_m0_hint_ddiv\n.hidden mk61_m0_hint_ddiv\n.type mk61_m0_hint_ddiv,%function\n.thumb_func\nmk61_m0_hint_ddiv:','regular_func __aeabi_ddiv')
block=block.replace('\n.size mk61_m0_hint_ddiv,.-mk61_m0_hint_ddiv\n','').replace('.global mk61_m0_hint_join\nmk61_m0_hint_join:\n','')
assert block.rstrip('\n')==oldblock.rstrip('\n')
for macro in ['mul32_32_64','muls32_32_64']:
 a=source.index('.macro '+macro+' ');z=source.index('.endm',a)+len('.endm');assert source[a:z]in control and source[a:z]in software
assert 'bl __aeabi_uidiv'not in software
sw=control[control.index('.Lrp2040_general_divisor:'):control.index('\n.size mk61_m0_hint_ddiv,')]
sw=sw.replace('.Lrp2040_general_divisor:','.global mk61_m0_ddiv_sw_from_guard\n.hidden mk61_m0_ddiv_sw_from_guard\n.type mk61_m0_ddiv_sw_from_guard,%function\n.thumb_func\nmk61_m0_ddiv_sw_from_guard:')
sw=sw.replace('push {r0-r3}','push {r0-r3,r7}').replace('pop {r0-r3}','pop {r0-r3,r7}')
sw=sw.replace('bl __aeabi_uidiv              @ !!! this could (but apparently does not) trash R12','bl mk61_m0_ddiv_seed17        @ exact quotient, explicitly preserves R12')
sw=sw.replace('mk61_m0_hint_join','mk61_m0_sw_join')
assert software[software.index('.global mk61_m0_ddiv_sw_from_guard'):software.index('\n.size mk61_m0_ddiv_sw_from_guard,')]==sw
assert '.equ use_hw_div,1'in control and '.equ use_hw_div,1'in candidate and'.equ use_hw_div,0'in software
assert (W/'seed17.S').read_bytes()==(S/'seed17.S').read_bytes()
assert (W/'LICENSE.TXT').read_bytes()==(R/'third_party/rp2040-softfloat/LICENSE.TXT').read_bytes()
ss=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(ss).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocs>','exec'),globals())
def alloc(e):return {n:(s[1],s[2],s[5],s[8],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
op=ElfImage(B/'RP-candidate.o');np=ElfImage(W/'RP-candidate.o');assert alloc(op)==alloc(np)
oldrels,newrels=relocs(op),relocs(np);changes=[]
for sec in alloc(op):
 a,b=oldrels.get(sec,[]),newrels.get(sec,[]);assert len(a)==len(b)
 changes.extend((sec,x,y)for x,y in zip(a,b)if x!=y)
assert len(changes)==1 and changes[0][0]=='.m0_pow_root_prefix'
assert changes[0][1][0:2]==changes[0][2][0:2]and changes[0][1][2]=='__aeabi_ddiv'and changes[0][2][2]=='mk61_m0_hint_ddiv'
call_offset=changes[0][1][0];assert call_offset==2732
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 c,n=[ElfImage(W/(context+'-'+v+'.o'))for v in ['control','candidate']];assert alloc(c)==alloc(n)and relocs(c)==relocs(n)
 if context!='RP':
  assert alloc(c)==alloc(ElfImage(B/(context+'-candidate.o')))
  for name in ['control-ddiv','candidate-ddiv','software','seed17']:assert not alloc(ElfImage(W/(context+'-'+name+'-disabled.o')))
images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']};resident=ElfImage(V/'firmware/mk61s-picocalc-pico-h.elf');tails={}
seed=ElfImage(S/'seed17.elf')
for label,e in images.items():
 start=e.symbols['mk61_m0_hint_join']&~1;end=(e.symbols['mk61_m0_hint_ddiv']&~1)+e.sizes['mk61_m0_hint_ddiv'];tails[label]=mem(e,start,end-start)
 s=e.symbols['mk61_m0_sw_join']&~1;z=(e.symbols['mk61_m0_ddiv_sw_from_guard']&~1)+e.sizes['mk61_m0_ddiv_sw_from_guard']
 assert tails[label]==mem(e,s,z-s)and len(tails[label])==282
 assert body(e,'mk61_m0_ddiv_seed17')==body(seed,'mk61_m0_ddiv_seed17')and e.sizes['mk61_m0_ddiv_seed17']==194
 assert e.named_sections['.ddiv'][3]+e.named_sections['.ddiv'][5]<0x10200000
 for section in ['.rootprefix','.tail']:
  s=e.named_sections[section];raw=e.bytes_at(s);baseline=mem(resident,s[3],s[5])
  if section=='.rootprefix':assert raw[:call_offset]==baseline[:call_offset]and raw[call_offset+4:]==baseline[call_offset+4:]
  else:assert raw==baseline
 assert e.bytes_at(e.named_sections['.front'])==ElfImage(B/'candidate.elf').bytes_at(ElfImage(B/'candidate.elf').named_sections['.front'])
assert tails['control']==tails['candidate']
assert hashlib.sha256(tails['candidate']).hexdigest()=='115b08286e1feb105ba6e2e3f3b254b68720372e3cf963fa02192befb9cb0c0b'
assert images['candidate'].named_sections['.ddiv'][5]==1050 and images['control'].named_sections['.ddiv'][5]==1038
# Compile from frozen sources into own output paths. Historical argv are never
# run in producer directories. Only explicit debug compilation-directory map.
build=json.loads((W/'build.json').read_text());d=O/'rebuild';d.mkdir();commands=[];outputs=[]
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','seed17.o','control.elf','candidate.elf'];mapping={str(W/n):str(d/n)for n in names}
for name in names:
 oldcmd=next(c for c in build['commands']if Path(c[c.index('-o')+1]).name==name);cmd=[mapping.get(s,s)for s in oldcmd]
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(W)]
 p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(name+'.stdout')).write_bytes(p.stdout);(d/(name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/name).read_bytes()==(W/name).read_bytes(),name
 commands.append(dict(argv=cmd,returncode=p.returncode));outputs.append(ref(d/name))
tc=Path(build['commands'][0][0]).parent
for name,expected in [('software.o',{'mk61_m0_ddiv_seed17'}),('seed17.o',set()),('candidate-ddiv.o',{'mk61_m0_ddiv_sw_from_guard','mk61_m0_ddiv_slow'})]:
 raw=subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(d/name)],text=True);assert {s.split()[-1]for s in raw.splitlines()}==expected,(name,raw)
script=O/'seed-only.ld';script.write_text('PHDRS { seed PT_LOAD FLAGS(5); }\nSECTIONS { .seed 0x10010000 : { KEEP(*(.m0_ddiv_seed17)) } :seed\n/DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) } }\n')
cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_ddiv_seed17','-T',str(script),str(d/'seed17.o'),'-o',str(O/'seed-only.elf')]
p=subprocess.run(cmd,cwd=O,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(dict(argv=cmd,returncode=0))
ownseed=ElfImage(O/'seed-only.elf');assert body(ownseed,'mk61_m0_ddiv_seed17')==body(images['candidate'],'mk61_m0_ddiv_seed17')
for name in ['candidate.elf','control.elf']:
 raw=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/name)]);(O/(name+'.actual.dis')).write_bytes(raw)
out=dict(status='PASS_SINGLE_ROOT_CALL_PRIVATE_CONTINUATION_SOURCE_ELF_AND_EIGHT_REBUILDS',refs=refs,
 local_pins=local,external_pins=external,counts=dict(local=81,external=1814),actual_parent='accepted Boundary128; near-one separate sibling',
 exact_one_source_BL_target_and_one_semantic_relocation=changes,
 unmodified_allocated_resident_code_except_actual_root_BL=True,other_ddiv_callers_original=True,
 private_clone_control_reversibly_exact_to_existing_BSD_kernel_source=True,only_DIRTY_branch_and12B_bridge_difference=True,
 common_tail282_byte_exact_all4copies=True,common_tail_SHA256=hashlib.sha256(tails['candidate']).hexdigest(),
 seed194_byte_exact_to_prior_exhaustive_seed=True,software_save20_for_alignment_preserves_raw_operand_words=True,
 original_normal_exponent_and_dyadic_guards_unchanged=True,default_M0_M4_selected_ASM_unchanged_12new_disabled_empty=True,
 candidate_allocation1050_includes_existing32byte_dyadic_constants=True,no_new_mathematical_tables_RAM_or_libgcc=True,
 own_eight_supplier_rebuilds_byte_exact=outputs,own_additional_seed_only_ELF=ref(O/'seed-only.elf'),commands=commands,
 all_writes_own_directory_and_original_commands_not_run_in_place=True,
 authoritative_source_paths_and_explicit_DWARF_compilation_directory_map=True,
 author_failed_import_preflight0_retained=ref(W/'HOST-PREFLIGHT-001.json'),
 source_proof_not_private_continuation_generic_ABI=True,shared_R12_merge_guard_still_required=True,
 ARM_calls=0,MPFR_inputs=0,device_IO=0,Git=0,network=0,canonical=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)
