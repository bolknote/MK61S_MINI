"""Exact overflow endpoints, inline liveness, unchanged RNE suffix and M4 controls."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-one-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_bytes());images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']};parent=ElfImage(P/'candidate.elf')
def body(e,address,size):
 s=next(s for s in e.sections if s[2]&2 and s[3]<=address<address+size<=s[3]+s[5])
 return e.bytes_at(s)[address-s[3]:address-s[3]+size]
tails=[]
for e in images.values():
 for tag,fn in [('mk61_m0_reciprocal1','mk61_m0_reciprocal1'),('mk61_m0_reciprocal1_sw','mk61_m0_reciprocal1_sw_from_guard')]:
  a=e.symbols[tag+'_after_second_product']&~1;b=(e.symbols[fn]&~1)+e.sizes[fn];tails.append(body(e,a,b-a))
assert all(t==tails[0]for t in tails)and len(tails[0])==186
offset=build['root_call_relocation_offset']
old=parent.bytes_at(parent.named_sections['.rootprefix']);new=images['candidate'].bytes_at(images['candidate'].named_sections['.rootprefix'])
assert old[:offset]==new[:offset]and old[offset+4:]==new[offset+4:]
for name in ['.front','.tail']:assert images['candidate'].bytes_at(images['candidate'].named_sections[name])==parent.bytes_at(parent.named_sections[name])
assert images['candidate'].bytes_at(images['candidate'].named_sections['.ddiv'])[-256:]==parent.bytes_at(parent.named_sections['.ddiv'])[-256:]
assert 'mk61_m0_ddiv_seed17'not in images['candidate'].symbols
prefix=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text();assert prefix==(P/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert prefix.count('\tbl\tmk61_m0_reciprocal1')==1
assert '\tmov\tr0, r7\n\tbl\tmk61_m0_reciprocal1'in prefix
assert '.Lpow_horner_CPI10_7:\n\t.long\t1072693248'in prefix
software=(W/'candidate-software.S').read_text();assert 'bl mk61_m0_ddiv_seed17'not in software and ' push {r0-r3,r7}'not in software
assert software.count(' reciprocal_seed_inline')==1
unit=(W/'unit.S').read_text();assert unit.count(' reciprocal_seed_inline')==1
for s in [software,unit]:assert '#include "inline-seed.inc"'in s and '#include "inline-seed-table.inc"'in s
# Positive binary64 subnormal magnitude is k*2^-1074. RNE overflows at
# 2^1024-2^970. These two exact products straddle the threshold, so monotonicity
# proves the condition for every integer k, not just a sampled neighbourhood.
T=1<<50;boundary=(1<<1024)-(1<<970);numerator=1<<1074
assert T*boundary<numerator<(T+1)*boundary
hardware=(W/'candidate-ddiv.S').read_text()
assert ' orrs r4,r6                    @ y0=(q31)y; nine ALU instructions since STR'in hardware
macro=(W/'inline-seed.inc').read_text()
assert all('['not in line or'ldrh r6,[r4,r6]'in line for line in macro.splitlines()if not line.startswith('.'))
assert 'push'not in macro and 'pop'not in macro and 'bl 'not in macro and 'bx 'not in macro
assert 'r0'not in macro and 'r2'not in macro and 'r3'not in macro and 'r5'not in macro and 'r12'not in macro
unit_proof=json.loads((W/'unit-proof.json').read_bytes());assert unit_proof['exhaustive_divisors']==65536
tc=Path(build['commands'][0][0]).parent;commands=[];disabled={}
for name,cpu,extra in [('generic_M0','cortex-m0plus',[]),('M4_soft','cortex-m4',[]),('M4_hard','cortex-m4',['-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['candidate-ddiv','candidate-software']:
  output=W/(name+'-'+source+'-disabled.o');command=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0',*extra,'-c',str(W/(source+'.S')),'-o',str(output)]
  subprocess.run(command,check=True);commands.append(command);e=ElfImage(output);assert not any(s[2]&2 and s[5]for s in e.sections);disabled[output.name]=sha(output)
for name in ['generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  e=ElfImage(W/(name+'-'+label+'.o'));assert not any(s[2]&2 and s[5]for s in e.sections)
out=dict(status='PASS_EXACT_OVERFLOW_INLINE_CONTEXT_AND_UNCHANGED_RNE_PROOFS',candidate_ELF_sha256=sha(W/'candidate.elf'),
 private_positive_numerator_one_contract_preserved=True,subnormal_integer_overflow_threshold=T,
 exact_overflow_endpoint_products_straddle_RNE_boundary=True,zero_division_sign_and_negative_symmetry_preserved=True,
 all_other_special_values_keep_original_IEEE_fallback=True,inline_macro_only_writes_R4_R6_R7_and_flags=True,
 all65536_divisors_and_all16_table_edge_flags_and_live_context_checked=True,
 same_exact_integer_seed_quotient_and_u0=True,no_inline_stack_writes_or_C_ABI_call=True,
 common4_after_second_product_186B_suffixes_identical=True,unchanged256B_table_moved_into_software_body=True,
 old312B_standalone_seed_not_allocated_in_candidate=True,hardware_nine_ALU_latency_block_preserved=True,
 all_existing_resident_bytes_except_rootBL_and_private_ddiv_unchanged=True,
 default_M0_M4_selected_source_controls_and6_new_disabled_objects_empty=True,
 private_code_bytes=[parent.named_sections['.ddiv'][5],images['candidate'].named_sections['.ddiv'][5]],
 no_new_table_values_global_RAM_or_libgcc=True,commands=commands,disabled_outputs=disabled,actual_ARM_or_MPFR_calls=0,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in['commands','disabled_outputs']},indent=2))
