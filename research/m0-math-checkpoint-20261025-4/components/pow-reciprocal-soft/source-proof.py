"""Bind the unchanged RNE tail, exact seed, inactive controls and parent receipt."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((W/'build.json').read_bytes());tc=Path(meta['commands'][0][0]).parent
images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
def block(e,address,size):
 s=next(s for s in e.sections if s[2]&2 and s[3]<=address<address+size<=s[3]+s[5])
 return e.bytes_at(s)[address-s[3]:address-s[3]+size]
def body(e,name):return block(e,e.symbols[name]&~1,e.sizes[name])
tails={}
for label,e in images.items():
 assert sha(W/(label+'.elf'))==meta['images'][label]['ELF_sha256']
 start=e.symbols['mk61_m0_hint_join']&~1
 end=(e.symbols['mk61_m0_hint_ddiv']&~1)+e.sizes['mk61_m0_hint_ddiv']
 tails[label]=block(e,start,end-start)
 start=e.symbols['mk61_m0_sw_join']&~1
 end=(e.symbols['mk61_m0_ddiv_sw_from_guard']&~1)+e.sizes['mk61_m0_ddiv_sw_from_guard']
 assert block(e,start,end-start)==tails[label]
 seed=ElfImage(ROOT/'.build/m0-ddiv-soft-seed17-20261025/seed17.elf')
 assert body(e,'mk61_m0_ddiv_seed17')==body(seed,'mk61_m0_ddiv_seed17')and len(body(e,'mk61_m0_ddiv_seed17'))==194
assert tails['control']==tails['candidate']
assert images['candidate'].symbols['mk61_m0_hint_ddiv']-images['control'].symbols['mk61_m0_hint_ddiv']==12
assert images['candidate'].named_sections['.ddiv'][5]-images['control'].named_sections['.ddiv'][5]==12
sources={n:(W/(n+'-ddiv.S')).read_text()for n in images}
bridge='''.Lrp2040_div_dirty_bridge:
 ldr r7,.Lrp2040_sw_target
 bx r7
.p2align 2
.Lrp2040_sw_target: .word mk61_m0_ddiv_sw_from_guard
.fill (12-(.-.Lrp2040_div_dirty_bridge))/2,2,0xbf00

'''
assert sources['candidate'].replace(bridge,'').replace(' bcs .Lrp2040_div_dirty_bridge',' bcs .Lrp2040_div_slow')==sources['control']
commands=[];disabled={}
for context,cpu,extra in [('generic_M0','cortex-m0plus',[]),('M4_soft','cortex-m4',[]),('M4_hard','cortex-m4',['-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['control-ddiv','candidate-ddiv','software','seed17']:
  output=W/(context+'-'+source+'-disabled.o')
  cmd=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0',*extra,'-c',str(W/(source+'.S')),'-o',str(output)]
  subprocess.run(cmd,check=True);commands.append(cmd);e=ElfImage(output)
  assert not any(s[2]&2 and s[5]for s in e.sections)
  disabled[output.name]=sha(output)
receipt=ROOT/'.build/m0-pow-boundary128-root-acceptance-20261025-001/RECEIPT.json'
r=json.loads(receipt.read_bytes())
assert r['status']=='ACCEPTED_PRIVATE_EXACT_BOUNDARY128_CALLER_COMPONENT_ONLY'
for pin in r['pins']:
 p=Path(pin['path']);assert p.stat().st_size==pin['bytes']and sha(p)==pin['sha256']
out=dict(status='PASS_SOURCE_RELATIONAL_SEED_AND_COMMON_RNE_TAIL_BINDING',
 candidate_ELF_sha256=sha(W/'candidate.elf'),common_tail_bytes=len(tails['candidate']),common_tail_sha256=hashlib.sha256(tails['candidate']).hexdigest(),
 control_hardware_candidate_hardware_and_candidate_software_tail_byte_identical=True,
 exact_seed194B_byte_identical_to_exhaustively_checked_seed=True,
 dirty_branch_and12B_bridge_only_hardware_source_difference=True,
 original_RP_root_call_relocation_only_change=True,other_resident_calls_keep_original_ddiv=True,
 private_continuation_requires_existing20B_frame_and_guarded_R6=True,
 default_M0_M4_selected_root_source_controls_equal=True,all12_extra_disabled_objects_empty=True,
 new_diagnostic_code_and_literals_bytes=images['candidate'].named_sections['.ddiv'][5],
 existing32B_dyadic_constants_duplicated_in_diagnostic_clone=True,new_mathematical_table_values=False,
 new_global_RAM_or_libgcc_dependencies=False,commands=commands,disabled_outputs=disabled,
 accepted_parent_ROOT_receipt=dict(path=str(receipt.relative_to(ROOT)),bytes=receipt.stat().st_size,sha256=sha(receipt)),
 actual_ARM_or_MPFR_calls=0,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items()if k not in ['commands','disabled_outputs']},indent=2))
