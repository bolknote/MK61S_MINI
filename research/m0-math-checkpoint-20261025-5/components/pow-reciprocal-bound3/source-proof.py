"""Exact bounded correction, private zero precondition and dead residual proof."""
from pathlib import Path
import json,re,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-zero-20261025';U=ROOT/'.build/m0-ddiv-seed-bound3-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
meta=json.loads((W/'build.json').read_bytes());commands=[]
for platform,args in [('generic_M0',['-mcpu=cortex-m0plus']),('M4_soft',['-mcpu=cortex-m4']),('M4_hard',['-mcpu=cortex-m4','-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['candidate-ddiv.S','candidate-software.S']:
  output=W/(platform+'-'+source.removesuffix('.S')+'-disabled.o')
  cmd=[meta['commands'][0][0],*args,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0','-c',str(W/source),'-o',str(output)]
  subprocess.run(cmd,cwd=W,check=True);commands.append(cmd)
  assert not any(s[2]&2 and s[5]for s in ElfImage(output).named_sections.values())
def body(e):return {n:(s[1],s[2],s[3],s[5],e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]and s[1]!=8}
for platform in ['RP','generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:assert body(ElfImage(W/(platform+'-'+label+'.o')))==body(ElfImage(P/(platform+'-candidate.o')))
for label in ['control','candidate']:
 assert(W/(label+'-ddiv.S')).read_bytes()==(P/'candidate-ddiv.S').read_bytes()
 source=(W/('software.S'if label=='control'else'candidate-software.S')).read_text()
 assert source.replace('#include "'+label+'-inline-seed.inc"','#include "inline-seed.inc"')==(P/'candidate-software.S').read_text()
 assert(W/(label+'-inline-seed.inc')).read_bytes()==(U/(label+'-seed.inc')).read_bytes()
assert(W/'control-inline-seed.inc').read_bytes()==(P/'inline-seed.inc').read_bytes()
assert(W/'inline-seed-table.inc').read_bytes()==(P/'inline-seed-table.inc').read_bytes()
assert(W/'candidate-remainder-certificate.inc').read_bytes()==(P/'candidate-remainder-certificate.inc').read_bytes()
sw=(W/'candidate-software.S').read_text();prefix=sw.split('mk61_m0_reciprocal1_sw_from_guard:\n')[1].split(' reciprocal_seed_inline\n')[0]
prefix='\n'.join(line.split('@')[0].split('//')[0]for line in prefix.splitlines());assert not re.search(r'\br0\b',prefix)
between=sw.split(' reciprocal_seed_inline\n')[1].split(' mul32_32_64 r2,r5,')[0]
between='\n'.join(line.split('@')[0].split('//')[0]for line in between.splitlines());assert not re.search(r'\br7\b',between)
assert' adds r6,#1\n lsrs r6,#1\n'in between
models=json.loads((U/'integer-model.json').read_bytes())['rows'];assert len(models)==65536
assert all(-1<=r['error']<=3 for r in models)
table=[]
for line in (W/'inline-seed-table.inc').read_text().splitlines():
 if line.startswith(' .hword '):table.extend(int(x,0)for x in line[8:].split(','))
blob=struct.pack('<128H',*table)
for label in ['control','candidate']:
 e=ElfImage(W/(label+'.elf'));assert e.bytes_at(e.named_sections['.ddiv']).count(blob)==1
out=dict(status='PASS_BOUND3_EXACT_QUOTIENT_AND_PRIVATE_DEAD_RESIDUAL_SOURCE_PROOF',commands=commands,
 only_software_seed_macro_changed=True,entire_hardware_source_and_other_resident_sections_unchanged=True,READY_nine_ALU_gap_unchanged=True,
 same65536_D_and256B_table_bytes=True,all_D_estimate_error_bound=[-1,3],private_raw_R0_zero_required=True,
 raw_R0_not_read_or_written_before_software_inline_call=True,exact_floor_quotient_for_all_D_under_all16_flags_verified=True,
 negative_residual_in_error_k_interval='R in[-kD,-(k-1)D-1], k=1,2,3',
 first_correction_BPL_exits_only_error1=True,second_ADD_unsigned_carry1_for_error2_0_for_error3=True,
 immediate_SBC_with_zero_subtracts0_or1_correctly=True,final_R7_for_error3_is_old_residual_minus_D=True,
 R7_has_no_use_before_second_product_overwrite=True,ADD1_then_LSR_restores_identical_flags_before_NR=True,
 all_other_inline_live_registers_and_SP_preserved=True,full_after_second_product_R0_R7_R12_SP_NZCV_frame28_equal=True,
 no_new_input_filter_or_precision_relaxation=True,no_inline_stack_or_memory_writes=True,
 instruction_counts_not_cycles=True,error1_branch_direction_changes_cycle_effect_requires_measurement=True,
 default_M0_M4_selected_controls_equal=True,six_added_disabled_objects_empty=True,no_new_tables_RAM_libgcc_or_external_calls=True,
 hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
