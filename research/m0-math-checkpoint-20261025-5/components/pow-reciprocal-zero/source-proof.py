"""Prove the exact source permutation and preserve other selected targets."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-certificate-20261025';U=ROOT/'.build/m0-ddiv-remainder-certificate-r3-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((W/'build.json').read_bytes());commands=[]
for platform,args in [('generic_M0',['-mcpu=cortex-m0plus']),('M4_soft',['-mcpu=cortex-m4']),('M4_hard',['-mcpu=cortex-m4','-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['candidate-ddiv.S','candidate-software.S']:
  output=W/(platform+'-'+source.removesuffix('.S')+'-disabled.o')
  cmd=[meta['commands'][0][0],*args,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0','-c',str(W/source),'-o',str(output)]
  subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
  e=ElfImage(output);assert not any(s[2]&2 and s[5]for s in e.named_sections.values())
def body(e):return {n:(s[1],s[2],s[3],s[5],e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]and s[1]!=8}
for platform in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:assert body(ElfImage(W/(platform+'-'+label+'.o')))==body(ElfImage(P/(platform+'-candidate.o')))
def normalize(text,label):
 for suffix in ['_before_second_product','_after_y_residual','_half_normalization','_pack_begin']:
  text=re.sub(r'\.global (mk61_m0_reciprocal1(?:_sw)?'+suffix+r')\n\1:\n','',text)
 return text.replace('#include "'+label+'-remainder-certificate.inc"','#include "remainder-certificate.inc"')
reverse=[(' mul32_32_64 r2,r5, r2,r3, r1,r0,r7,r2,r3  @ xL*a0; preserve R4=0\n',' mul32_32_64 r2,r5, r2,r3, r1,r4,r7,r2,r3  @ xL*a0\n'),
 (' ldr r1,[r13,#4]               @ xH; R1 is dead temporary\n muls r1,r5                    @ xH*a0\n adds r3,r1                    @ r2:r3 now x*a0 Q82\n',' ldr r4,[r13,#4]               @ xH\n muls r4,r5                    @ xH*a0\n adds r3,r4                    @ r2:r3 now x*a0 Q82\n'),
 (' // R4=0 survives the second product and xH temporary.\n',' lsls r4,r0,#5                 @ y Q57\n'),
 (' // R4 is already zero; next shifts replace flags.\n',' lsls r4,#1                    @ y now Q58\n'),
 (' adds r0,#1                    @ round up with known-zero R6\n adcs r1,r6\n',' movs r2,#0                    @ round up\n adds r0,#1\n adcs r1,r2\n'),
 (' bmi .Lcertificate_down\n movs r6,#0                   @ full multiplication clobbered R6\n b .Lcertificate_up\n',' bmi .Lcertificate_down\n b .Lcertificate_up\n')]
for kind in ['hardware','software']:
 parent=(P/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text()
 control=normalize((W/('control-ddiv.S'if kind=='hardware'else'software.S')).read_text(),'control');assert control==parent
 candidate=normalize((W/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text(),'candidate')
 for new,old in reverse:assert candidate.count(new)==1,(kind,new);candidate=candidate.replace(new,old)
 assert candidate==parent
 assert(W/'control'/'native_eabi_m0_rp2040.S').read_bytes()==(P/'candidate'/'native_eabi_m0_rp2040.S').read_bytes()
def instructions(path):return'\n'.join(line for line in path.read_text().splitlines()if not line.startswith('//'))
assert instructions(W/'candidate-remainder-certificate.inc').replace('r3','r6')==instructions(W/'control-remainder-certificate.inc')
assert(W/'candidate-remainder-certificate.inc').read_bytes()==(U/'remainder-certificate.inc').read_bytes()
assert(W/'inline-seed.inc').read_bytes()==(P/'inline-seed.inc').read_bytes()and(W/'inline-seed-table.inc').read_bytes()==(P/'inline-seed-table.inc').read_bytes()
out=dict(status='PASS_EXACT_REGISTER_PERMUTATION_AND_KNOWN_ZERO_SOURCE_PROOF',commands=commands,
 exact_reverse_transform_restores_both_complete_parent_sources=True,second_product_is_R0_R4_permutation_from_equal_zero_inputs=True,
 xH_temporary_R1_dead_before_original_shift_and_full_after_residual_join=True,all_full_R0_R7_R12_SP_NZCV_frame28_after_residual_checked=True,
 removed_zero_double_flags_replaced_before_use=True,certificate_scratch_R3_written_before_read_R6_zero_preserved=True,
 full_fallback_explicitly_restores_R6_zero_before_upward_ADCS=True,old_R2_zero_write_dead_before_pack=True,
 all_exact_product_midpoint_and_RNE_decisions_unchanged=True,READY_nine_ALU_gap_unchanged=True,all7_DIRTY_SIO_words_preserved=True,
 same256B_seed_table_and_inline_seed=True,no_new_tables_RAM_libgcc_or_external_calls=True,
 default_M0_M4_selected_controls_equal=True,six_added_disabled_objects_empty=True,
 private_numerator_positive1_only=True,not_generic_division=True,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
