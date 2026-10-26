"""Bind frozen selected LUT suffix and rebuild solely into own directory."""
import hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-lut-20261025';P=R/'.build/m0-pow-reciprocal-soft-20261025';S=R/'.build/m0-ddiv-seed-lut-20261025'
sys.path.insert(0,str(R/'tests'));from check_stm32_vectors import ElfImage
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def pin(p,h):
 v=ref(p);assert v['sha256']==h,v;return v
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def mem(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def allocated(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
refs=dict(FROZEN=pin(W/'FROZEN.json','7384323f37dae2fb8a7cf350a64165392181e20276e83551ccf9ef320d811ffc'),
 result=pin(W/'result.json','42885850b0f63623ce4371ae3471b5fa262458e23bde5f7a798114c944ce0031'),
 HANDOFF=pin(W/'HANDOFF.md','91e07f733a60856817e89fd8d31a008b11c6de9efd9c6abdba053940044243e0'),
 ELF=pin(W/'candidate.elf','e5247764b40a409598f1ebbe7f8a46d9e52544a611ba7ec2d40d183e6c4e96e5'),
 parent_FROZEN=pin(P/'FROZEN.json','13dc7f8186d4678fac6b7a0da0b27e00dbb678316e292d320d3eefdd35dbba0c'),
 parent_independent=pin(R/'.build/m0-pow-reciprocal-soft-independent-20261025/FINAL-REVIEW.json','211cf956001390c4f0b894a9979ca8aa640cfe7a5d33082fdfe6cc497268c3e0'),
 parent_ROOT_later_additive=pin(R/'.build/m0-pow-reciprocal-soft-root-acceptance-20261025-001/RECEIPT.json','de2f15995d64baa1e7e68aec9d45cc90efa43264ce1cf5985fb3fc7d6849372c'),
 seed_study_FROZEN=pin(S/'FROZEN.json','ebddb871e62fbdaeedd2f24a7ebeff506eb4d2ea6ee4a9d30bb1fff27fc9e955'))
local=[];external=[];study=[]
for manifest,base,items in [(W/'FROZEN.json',W,local),(W/'source-lineage-pins.json',R,external),(S/'FROZEN.json',S,study)]:
 for n,d in json.loads(manifest.read_text())['files'].items():
  assert not n.startswith('/')and'..'not in Path(n).parts and'.git'not in Path(n).parts
  v=ref(base/n);assert [v['bytes'],v['sha256']]==[d['bytes'],d['sha256']],v;items.append(v)
assert len(local)==67 and len(external)==1978
assert json.loads((W/'result.json').read_text())['parent_ROOT_receipt']is None
for label in ['control','candidate']:
 for n in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:
  assert (W/label/n).read_bytes()==(P/'candidate'/n).read_bytes()
 assert (W/(label+'-ddiv.S')).read_bytes()==(P/'candidate-ddiv.S').read_bytes()
 assert (W/(label+'.ld')).read_bytes()==(P/'candidate.ld').read_bytes()
for n in ['software.S','LICENSE.TXT']:assert (W/n).read_bytes()==(P/n).read_bytes()
assert (W/'control-seed17.S').read_bytes()==(P/'seed17.S').read_bytes()
assert (W/'candidate-seed17.S').read_bytes()==(S/'lut128_floor.S').read_bytes()
selection=json.loads((S/'selection.json').read_text());assert selection['selected']=='lut128_floor'
build=json.loads((W/'build.json').read_text());assert build['selection_sha256']==ref(S/'selection.json')['sha256']and build['bare_unit_proof_sha256']==ref(S/'unit-proof.json')['sha256']
old=ElfImage(P/'candidate.elf');control=ElfImage(W/'control.elf');new=ElfImage(W/'candidate.elf');unit=ElfImage(S/'lut128_floor.elf')
assert allocated(old)==allocated(control)
assert allocated(old).keys()==allocated(new).keys()and [n for n in allocated(old)if allocated(old)[n]!=allocated(new)[n]]==['.ddiv']
seed=old.symbols['mk61_m0_ddiv_seed17']&~1;assert new.symbols['mk61_m0_ddiv_seed17']&~1==seed and seed%4==0
sec=old.named_sections['.ddiv'];offset=seed-sec[3]
assert mem(old,sec[3],offset)==mem(new,sec[3],offset)
assert sec[5]==1050 and new.named_sections['.ddiv'][5]==1168 and offset+194==1050 and offset+312==1168
assert new.sizes['mk61_m0_ddiv_seed17']==56 and mem(new,seed,312)==unit.bytes_at(unit.named_sections['.seed'])
table=struct.unpack('<128H',mem(new,seed+56,256));expected=tuple((1<<32)//(65536+512*i+256)for i in range(128));assert table==expected
for n in ['mk61_m0_hint_ddiv','mk61_m0_hint_join','mk61_m0_ddiv_sw_from_guard','mk61_m0_sw_join']:
 assert old.symbols[n]==control.symbols[n]==new.symbols[n]
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:assert allocated(ElfImage(W/(context+'-'+label+'.o')))==allocated(ElfImage(P/(context+'-candidate.o')))
 if context!='RP':assert not allocated(ElfImage(W/(context+'-seed-disabled.o')))
names=['RP-control.o','RP-candidate.o','control-ddiv.o','candidate-ddiv.o','software.o','control-seed17.o','candidate-seed17.o','control.elf','candidate.elf']
d=O/'rebuild';d.mkdir();mapping={str(W/n):str(d/n)for n in names};commands=[];outputs=[]
for n in names:
 argv=next(c for c in build['commands']if Path(c[c.index('-o')+1]).name==n);cmd=[mapping.get(s,s)for s in argv]
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 if '-g'in cmd:cmd+=['-fdebug-prefix-map='+str(O)+'='+str(W)]
 p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(n+'.stdout')).write_bytes(p.stdout);(d/(n+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert (d/n).read_bytes()==(W/n).read_bytes(),n
 commands.append(dict(argv=cmd,returncode=p.returncode));outputs.append(ref(d/n))
tc=Path(build['commands'][0][0]).parent
script=O/'seed-only.ld';script.write_text('PHDRS { seed PT_LOAD FLAGS(5); }\nSECTIONS { .seed 0x10010000 : { KEEP(*(.m0_ddiv_seed17)) } :seed\n/DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) } }\n')
cmd=[str(tc/'arm-none-eabi-ld'),'--gc-sections','-e','mk61_m0_ddiv_seed17','-T',str(script),str(d/'candidate-seed17.o'),'-o',str(O/'seed-only.elf')]
p=subprocess.run(cmd,cwd=O,capture_output=True);assert p.returncode==0,p.stderr.decode();commands.append(dict(argv=cmd,returncode=0))
own=ElfImage(O/'seed-only.elf');assert mem(own,0x10010000,312)==mem(new,seed,312)
assert not subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(d/'candidate-seed17.o')],text=True).strip()
for n in ['control.elf','candidate.elf']:(O/(n+'.actual.dis')).write_bytes(subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(d/n)]))
out=dict(status='PASS_EXACT_SELECTED_LUT_SUFFIX_TABLE_SOURCE_BINDING_AND_NINE_REBUILDS',refs=refs,local=local,external=external,study=study,
 local_count67=True,external_count1978=True,study_local_count=len(study),parent_ROOT_at_child_seal_None_preserved_later_receipt_additive_only=True,
 all_sources_except_seed_exact_to_soft_parent=True,all_other_allocated_bytes_addresses_and_entrypoints_unchanged=True,
 selected56byte_code256byte_table312suffix_matches_tested_unit=True,table128u16_formula_and_littleendian_bytes_exact=True,
 seed_address=seed,table_address=seed+56,seed4aligned=True,table_halfword_and4aligned=True,only_new_R3_leaf_contract_requires_fresh_caller_proof=True,
 old_diagnostic1050_new1168_delta118=True,new_mathematical_table_values256B=True,no_new_RAM_libgcc=True,
 default_M0_M4_selected_objects_unchanged_new3disabled_empty=True,own_nine_byteexact_rebuilds=outputs,own_extra_seed_only_ELF=ref(O/'seed-only.elf'),commands=commands,
 own_outputs_only_original_commands_not_inplace=True,debug_prefix_map_explicit=True,
 author_failed_calibration24_ARM3_MPFR_preserved=ref(W/'PREFLIGHT-001.json'),
 no_generic_private_continuation_ABI=True,ARM_calls=0,MPFR_inputs=0,device_IO=0,Git=0,canonical=0,network=0,integration_GO=False)
print(json.dumps(save('binding.json',out)),flush=True)
