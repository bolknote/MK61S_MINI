"""Authoritative r2 seal/source/object/ELF review; outputs remain here only."""
import ast,difflib,hashlib,json,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-square128-r2-20261025';OLD=R/'.build/m0-pow-square128-20261025';P=R/'.build/m0-asin-scaled-bound-v164-20261023';BASE=R/'.build/m0-pow-exp-table-product-20261025'
sys.path.insert(0,str(R/'tests'))
from check_stm32_vectors import ElfImage
def ref(p):p=Path(p);d=p.read_bytes();return dict(path=str(p),bytes=len(d),sha256=hashlib.sha256(d).hexdigest())
def pin(p,h):v=ref(p);assert v['sha256']==h,v;return v
def save(n,d):
 if (O/n).exists():
  assert json.loads((O/n).read_text())==json.loads(json.dumps(d));return ref(O/n)
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 return ref(O/n)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
refs=dict(FROZEN=pin(W/'FROZEN.json','31de9242e96642ed7de050a2a7a51a5baeacdd9c8842e4b0d7f3f2c74e2e681d'),
 result=pin(W/'result.json','e8cf0f97d32cc40dde177a2d6f6d5a9c22cb4afd56ff88abb694716418050152'),
 HANDOFF=pin(W/'HANDOFF.md','e9517967bfedbaa8edcd9ecc517511d27f5c8ea1c90091d915548f9fdaf191ee'),
 ELF=pin(W/'candidate.elf','6325d6e1d2d619028f9cb7d156c688ead1795331513941207e9c3de2c1214898'),
 parent_review=pin(R/'.build/m0-pow-exp-table-product-independent-20261025/FINAL-REVIEW.json','eabfbb18bc14d07c506c1daa49bfdae499f1cce7461682b5f44d589e4d169dc3'),
 parent_ROOT=pin(R/'.build/m0-pow-exp-table-product-root-acceptance-20261025-001/RECEIPT.json','09b8c7326b37b67e106ff517cc594dc02d09fa0643ed96dee47c48af747f6d4d'))
local=[]
for n,row in json.loads((W/'FROZEN.json').read_text())['files'].items():
 v=ref(W/n);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];local.append(v)
assert len(local)==69
external=[]
for n,row in json.loads((W/'source-lineage-pins.json').read_text())['files'].items():
 p=R/n;assert '/dev/'not in str(p)and '/.git/'not in str(p)
 v=ref(p);assert v['bytes']==row['bytes']and v['sha256']==row['sha256'];external.append(v)
assert len(external)==1585
# First seal remains rejected. Independently determine exactly which pin failed.
rejected=pin(W/'REJECTED-SEAL-001.json','2f8310755224d63b246743976692f13b396d40bedfc31a619711f6926791d80c')
assert (W/'REJECTED-SEAL-001.json').read_bytes()==(OLD/'FROZEN.json').read_bytes()
bad=[];copy_differences=[]
for n,row in json.loads((W/'REJECTED-SEAL-001.json').read_text())['files'].items():
 v=ref(OLD/n)
 if v['bytes']!=row['bytes']or v['sha256']!=row['sha256']:bad.append(dict(name=n,old_pin=row,actual=v))
 if (W/n).read_bytes()!=(OLD/n).read_bytes():copy_differences.append(n)
assert [v['name']for v in bad]==['finalize.log']and copy_differences==['HANDOFF.md','source-lineage-pins.json']
old_lineage=json.loads((OLD/'source-lineage-pins.json').read_text())['files'];new_lineage=json.loads((W/'source-lineage-pins.json').read_text())['files']
assert len(old_lineage)==1516 and all(new_lineage.get(k)==v for k,v in old_lineage.items())
added_lineage={k:v for k,v in new_lineage.items()if k not in old_lineage}
assert len(added_lineage)==69 and all(k.startswith('.build/m0-pow-square128-20261025/')or k=='.build/m0-pow-square128-seal-r2-20261025.py'for k in added_lineage)
assert (W/'HANDOFF.md').read_bytes().startswith((OLD/'HANDOFF.md').read_bytes())
assert bad[0]['old_pin']['bytes']==0 and bad[0]['actual']['bytes']==376
assert bad[0]['actual']['sha256']=='03b995e502337c8c5b0cc71f1e88777c67491d4da3882951251d8950d1980f16'
reissue=save('seal-lineage.json',dict(status='PASS_HONEST_R2_REISSUE_FIRST_SEAL_REJECTED',authoritative=refs['FROZEN'],rejected_historical_seal=rejected,
 independently_found_bad_first_seal_pins=bad,copy_differences=copy_differences,HANDOFF_metadata_append_only=True,
 lineage_metadata_amplification=dict(old_pins_retained_unchanged=1516,added_historical_producer_and_sealer_refs=added_lineage,new_total=1585),
 all_other_sources_binaries_raw_proofs_results_and_completed_log_bytecopy=True,old_producer_not_rewritten=True,
 copied_ARM_and_MPFR_counts_not_fresh=True,first_seal_not_accepted=True))
old=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text();new=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert old==(P/'source/code/native_eabi_m0_pow_root_prefix.inc').read_text()
a=old.index('\t.section\t.m0_pow_square_fixed,');z=old.index('\t.section\t.m0_pow_root_prefix,',a+1)
assert new==old[:a]+(W/'square128.S.inc').read_text()+'\n'+old[z:]
patch=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/code/native_eabi_m0_pow_root_prefix.inc',tofile='b/code/native_eabi_m0_pow_root_prefix.inc'))
assert patch==(W/'square128-only.patch').read_text()
assert (W/'candidate/native_eabi_m0_rp2040.S').read_bytes()==(W/'control/native_eabi_m0_rp2040.S').read_bytes()==(P/'source/code/native_eabi_m0_rp2040.S').read_bytes()
s=(R/'.build/m0-exp-cached-product-independent-20261024/bind_rebuild.py').read_text();fn=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef)and n.name=='relocs')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-semantic-relocs>','exec'),globals())
def allocated(im):return {n:(s[1],s[2],s[5],s[8],None if s[1]==8 else im.bytes_at(s))for n,s in im.named_sections.items()if s[2]&2 and s[5]}
for context in ['RP','generic_M0','M4_soft','M4_hard']:
 c,n=[ElfImage(W/(context+'-'+label+'.o'))for label in ['control','candidate']];cc,nn=allocated(c),allocated(n)
 if context=='RP':
  assert cc.keys()==nn.keys()and [k for k in cc if cc[k]!=nn[k]]==['.m0_pow_square_fixed']
  assert cc['.m0_pow_square_fixed'][:4]==nn['.m0_pow_square_fixed'][:4]
  for section,rows in relocs(c).items():
   if section in cc and section!='.m0_pow_square_fixed':assert rows==relocs(n)[section]
 else:assert cc==nn and relocs(c)==relocs(n)
resident=ElfImage(P/'firmware/mk61s-picocalc-pico-h.elf');entry=resident.symbols['pow_integer128_square']&~1;helper=resident.symbols['pow_integer128_approx_high64']&~1
for label in ['control','candidate']:
 im=ElfImage(W/(label+'.elf'));unit=ElfImage(W/('unit-'+label+'.elf'))
 assert im.symbols['pow_integer128_square']&~1==entry and memory(im,entry,310)==memory(unit,entry,310)
 assert memory(unit,helper,94)==memory(resident,helper,94)
 if label=='control':assert memory(im,entry,310)==memory(resident,entry,310)
 else:assert im.sizes['pow_integer128_square']==232 and memory(im,entry+232,78)==bytes.fromhex('00bf')*39
# Rebuild with all outputs redirected here and inputs rebound to authoritative
# r2 copies. Historical producer argv are evidence, never executed in place.
build=json.loads((W/'build.json').read_text());unitbuild=json.loads((W/'unit-build.json').read_text());d=O/'rebuild';d.mkdir(exist_ok=True);commands=[];rebuilt=[]
selected=[c for c in build['commands']if Path(c[c.index('-o')+1]).name=='RP-candidate.o']
selected+=[c for c in unitbuild['commands']if Path(c[c.index('-o')+1]).name=='helper.o']
selected+=[c for c in build['commands']if Path(c[c.index('-o')+1]).name=='candidate.elf']
selected+=[c for c in unitbuild['commands']if Path(c[c.index('-o')+1]).name=='unit-candidate.elf']
assert len(selected)==4
for historical in selected:
 cmd=list(historical);oldout=Path(cmd[cmd.index('-o')+1]);output=d/oldout.name
 assert not any(x in cmd for x in ['-MD','-MMD','-MF','-save-temps'])
 cmd=[str(W/Path(x).relative_to(OLD))if x.startswith(str(OLD)+'/')else x for x in cmd]
 cmd[cmd.index('-o')+1]=str(output)
 cmd=[str(d/Path(x).name)if x in [str(W/'RP-candidate.o'),str(W/'helper.o')]else x for x in cmd]
 if '-g'in cmd:
  cmd+=['-fdebug-prefix-map='+str(W)+'='+str(OLD),'-fdebug-prefix-map='+str(O)+'='+str(OLD)]
 p=subprocess.run(cmd,cwd=O,capture_output=True);(d/(oldout.name+'.stdout')).write_bytes(p.stdout);(d/(oldout.name+'.stderr')).write_bytes(p.stderr)
 assert p.returncode==0,p.stderr.decode();assert output.read_bytes()==(W/oldout.name).read_bytes(),oldout
 commands.append(cmd);rebuilt.append(ref(output))
tc=Path(build['commands'][0][0]).parent
for label in ['control','candidate']:
 text=subprocess.check_output([str(tc/'arm-none-eabi-objdump'),'-d',str(W/('unit-'+label+'.elf'))])
 (O/(label+'.actual.dis')).write_bytes(text)
out=dict(status='PASS_AUTHORITATIVE_R2_SINGLE_SLOT_BINDING_AND_4_BYTEEXACT_REBUILDS',accepted_refs=refs,local=local,external=external,
 local_count=69,external_count=1585,seal_lineage=reissue,actual_parent='accepted table-product dd0ec366; near-one separate sibling',
 exact_one_root_prefix_function_replacement=True,all_other_source_allocated_bytes_semantic_relocations_BSS_unchanged=True,
 selected_defaultM0_M4soft_hard_ASM_unchanged=True,slot310_unchanged_actual_function310_to232=True,unchanged_helper94=True,
 four_own_whole_object_helper_ELF_unit_rebuilds=rebuilt,rebuild_argv=commands,historical_commands_not_executed_over_producer=True,
 authoritative_r2_source_inputs_with_explicit_DWARF_prefix_remapping_to_historical_paths=True,
 fresh_unit_disassembly={n:ref(O/(n+'.actual.dis'))for n in ['control','candidate']},entry=entry,helper=helper,
 source_merge_R12_loader_layout_guards_still_required=True,integration_GO=False,device_IO=0,Git=0,canonical=0,network=0)
print(json.dumps(dict(binding=save('binding.json',out),rebuilds=4),indent=2))
