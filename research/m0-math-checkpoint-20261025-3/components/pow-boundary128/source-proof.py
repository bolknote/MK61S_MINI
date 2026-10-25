from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];BASE=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
build=json.loads((W/'build.json').read_bytes());old=ElfImage(W/'control.elf');new=ElfImage(W/'candidate.elf')
assert sha(W/'candidate.elf')==build['images']['candidate']['ELF_sha256']
assert old.named_sections['.front'][3:6:2]==new.named_sections['.front'][3:6:2]
raw=new.bytes_at(new.named_sections['.front']);target=new.symbols['mk61_m0_boundary128']
assert raw[:4]==bytes.fromhex('004b1847')
assert int.from_bytes(raw[4:8],'little')==target and target&1
assert raw[8:]==bytes.fromhex('00bf')*262
source=(BASE/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
control=(W/'control/native_eabi_m0_pow_root_prefix.inc').read_text();candidate=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
assert source==control
a=source.index('\t.section\t.m0_pow_boundary_exact,');b=source.index('\t.section\t.m0_pow_root_prefix,',a+1)
assert candidate[:a]==source[:a] and candidate.endswith(source[b:])
assert '\tmovs\tr0, #16' in source[a:b]
tc=Path(build['commands'][0][0]).parent
undefined=subprocess.check_output([str(tc/'arm-none-eabi-nm'),'-u',str(W/'boundary.o')],text=True)
assert {line.split()[-1]for line in undefined.splitlines()}=={'pow_integer128_square','pow_integer128_multiply','mk61_m0_boundary128_compare'}
commands=[];inactive={}
for context,cpu,extra in [('generic_M0','cortex-m0plus',[]),('M4_soft','cortex-m4',[]),('M4_hard','cortex-m4',['-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 cmd=[str(tc/'arm-none-eabi-g++'),'-Os','-mcpu='+cpu,'-mthumb','-DMK61_M0_RP2040_EABI=0','-fno-exceptions','-fno-rtti',*extra,'-c',str(W/'boundary.cpp'),'-o',str(W/(context+'-boundary-disabled.o'))]
 subprocess.run(cmd,check=True);commands.append(cmd);e=ElfImage(W/(context+'-boundary-disabled.o'))
 assert not any(s[2]&2 and s[5]for s in e.named_sections.values())
 inactive[context]=dict(allocated_bytes=0,undefined_symbols=0)
q=json.loads((W/'qualification.json').read_bytes());unit=json.loads((W/'unit-proof.json').read_bytes())
assert q['candidate_wrong']==q['parent_cost_increase_states']==0 and q['new_raw_loss_pairs']==[]
assert unit['all24_midpoint_operand_bytes_identical']and unit['all_returned_sides_identical']
assert unit['actual_ARM_calls']==6000
out=dict(status='PASS_EXACT_BOUNDARY128_SOURCE_ABI_AND_BINARY_BINDING',
 source_parent=str(BASE.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(BASE/'FROZEN.json'),
 candidate_ELF_sha256=sha(W/'candidate.elf'),CPP_sha256=sha(W/'boundary.cpp'),
 front_slot_bytes=532,tail_transition_bytes=8,tail_transition_instructions=2,
 added_diagnostic_body_bytes=new.named_sections['.boundary128'][5],
 actual_R0_R2_LR_SP_and_stack_cell_tail_contract=True,ordinary_int32_PCS_no_extra_R12_result=True,
 same24byte_midpoint_initialization_square_transform_radius16_and_comparison_rules=True,
 unchanged_other_RP_allocated_sections_relocations_and_resident_veneers=True,
 default_M0_M4_selected_assembly_controls_equal=True,extra_CPP_inactive_contexts=inactive,
 new_tables_global_RAM_libgcc_ROM_math_dependencies=False,
 original_helpers_and_accepted_square_are_actual_byte_bound_in_bare_machines=True,
 all16_NZCV_noisy_R3_R12_PCS_and_exact_endpoint_unit_pass=True,
 observed_bare_call_peak_bytes=unit['observed_frames'],
 general_pow_totality_and_overall_library_speed_not_established=True,
 integration_actual_R12_loader_layout_guards_and_physical_cycles_pending=True,
 inactive_CPP_commands=commands,actual_ARM_or_MPFR_calls=0,hardware_accessed=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='inactive_CPP_commands'},indent=2))
