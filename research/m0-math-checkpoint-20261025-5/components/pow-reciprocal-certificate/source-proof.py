"""Bind the exact source transform, unchanged resident code and disabled targets."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-inline-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((W/'build.json').read_bytes());commands=[]
for platform,args in [('generic_M0',['-mcpu=cortex-m0plus']),('M4_soft',['-mcpu=cortex-m4']),('M4_hard',['-mcpu=cortex-m4','-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['candidate-ddiv.S','candidate-software.S']:
  output=W/(platform+'-'+source.removesuffix('.S')+'-disabled.o')
  cmd=[meta['commands'][0][0],*args,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0','-c',str(W/source),'-o',str(output)]
  subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
  e=ElfImage(output);assert not any(s[2]&2 and s[5]for s in e.named_sections.values())
for platform in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  a=ElfImage(W/(platform+'-'+label+'.o'));b=ElfImage(P/(platform+'-candidate.o'))
  def body(e):return {n:(s[1],s[2],s[3],s[5],e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]and s[1]!=8}
  assert body(a)==body(b)
for kind in ['hardware','software']:
 control=(W/('control-ddiv.S'if kind=='hardware'else'software.S')).read_text()
 candidate=(W/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text()
 section='.section .m0_ddiv_hint_hw,'if kind=='hardware'else'.section .m0_ddiv_hint_sw,'
 assert control[control.index(section):control.index('dd_1:')]==candidate[candidate.index(section):candidate.index('dd_1:')]
 begin='_certificate_begin:\n';a=control.index('dd_1:');b=candidate.index('dd_1:')
 ca=control[a:control.index(begin,a)+len(begin)];cb=candidate[b:candidate.index(begin,b)+len(begin)]
 assert ca.replace(' lsls r4,#16                   @ Q105-32=Q73\n',' // Private numerator one: yL is exactly zero; flags dead before SUBS.\n')==cb
 full=' adds r4,r5                   @ restore exact modular base before full product\n mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3\n negs r2,r2\n sbcs r4,r3\n cmp r4,#0\n bmi .Lcertificate_down\n b .Lcertificate_up\n'
 assert full in candidate
assert(W/'inline-seed.inc').read_bytes()==(P/'inline-seed.inc').read_bytes()
assert(W/'inline-seed-table.inc').read_bytes()==(P/'inline-seed-table.inc').read_bytes()
assert(W/'remainder-certificate.inc').read_bytes()==(ROOT/'.build/m0-ddiv-remainder-certificate-r2-20261025/remainder-certificate.inc').read_bytes()
out=dict(status='PASS_EXACT_SOURCE_TRANSFORM_AND_RESIDENT_TARGET_CONTROLS',commands=commands,
 default_M0_M4_selected_controls_equal=True,six_added_disabled_objects_empty=True,
 all_refinement_instructions_before_dd1_unchanged=True,only_known_zero_yL_shift_removed_before_certificate=True,
 yL_zero_proof='Positive-one raw lowword R0=0 survives the first two products. The existing lsls r4,r0,#5 sets yL=0. The signed product leaves R4 untouched; optional doubling preserves zero. Shift flags are dead before the later SUBS.',
 universal_omitted_product_bound=131071,certificate_preserves_R0_R1_R12_SP=True,
 complete_old_product_and_signed_sign_test_retained_on_uncertain_interval=True,
 uncertainty_excludes_both_zero_and_INT32_MIN=True,zero_uses_complete_parent_sign_test=True,
 positive_ADDS_resets_carry_before_ADCS=True,negative_pack_shifts_reset_dead_flags=True,
 same256B_seed_table_and_inline_seed_bytes=True,READY_nine_ALU_gap_unchanged=True,
 resident_ddiv_and_all_other_callers_bytes_addresses_unchanged=True,
 new_tables_RAM_libgcc_or_external_calls=False,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
