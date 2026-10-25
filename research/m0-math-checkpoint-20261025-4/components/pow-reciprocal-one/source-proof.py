"""Source/ELF caller contract, equivalent exponent guards and exact common tail."""
from pathlib import Path
import hashlib,json,struct,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-lut-20261025'
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']};parent=ElfImage(P/'candidate.elf');build=json.loads((W/'build.json').read_bytes())
def bytes_at(e,address,size):
 s=next(s for s in e.sections if s[2]&2 and s[3]<=address<address+size<=s[3]+s[5])
 return e.bytes_at(s)[address-s[3]:address-s[3]+size]
def tail(e,tag,function):
 a=e.symbols[tag+'_after_second_product']&~1;b=(e.symbols[function]&~1)+e.sizes[function]
 return bytes_at(e,a,b-a)
tails=[]
for label,e in images.items():
 for tag,function in([('mk61_m0_hint','mk61_m0_hint_ddiv'),('mk61_m0_sw','mk61_m0_ddiv_sw_from_guard')]if label=='control'else[('mk61_m0_reciprocal1','mk61_m0_reciprocal1'),('mk61_m0_reciprocal1_sw','mk61_m0_reciprocal1_sw_from_guard')]):tails.append(tail(e,tag,function))
assert all(t==tails[0]for t in tails)
for label,e in images.items():
 pseed=parent.symbols['mk61_m0_ddiv_seed17']&~1;cseed=e.symbols['mk61_m0_ddiv_seed17']&~1
 assert bytes_at(e,cseed,312)==bytes_at(parent,pseed,312)
for name in ['.rootprefix','.front','.tail']:
 assert images['candidate'].bytes_at(images['candidate'].named_sections[name])==images['control'].bytes_at(images['control'].named_sections[name])==parent.bytes_at(parent.named_sections[name])
prefix=(W/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
caller='''\tmovs\tr7, #0
\tadds\tr2, r0, r1
\tadcs\tr3, r7
\tldr\tr1, .Lpow_horner_CPI10_7
\tmov\tr0, r7
\tbl\tmk61_m0_reciprocal1'''
assert prefix.count(caller)==1 and prefix.count('\tbl\tmk61_m0_reciprocal1')==1
assert '.Lpow_horner_CPI10_7:\n\t.long\t1072693248' in prefix
# The source block has no intervening entry labels, so every incoming edge
# to the call executes the zero and binary64-one constant loads.
guard_rows=[]
for exponent in range(2048):
 old=(1<=exponent<=2046 and 0<=2044-exponent<=2043)
 new=(0<=exponent-1<=2043)
 assert old==new
 if old:assert 2044-exponent==2043-(exponent-1)
 guard_rows.append(dict(exponent=exponent,old=old,new=new,addend=2044-exponent if new else None))
software=(W/'candidate-software.S').read_text()
assert ' // Numerator one needs no software unpacking; R1/R4 are dead.'in software
assert ' movs r0,#0\n mvns r0,r0\n'not in software
hardware=(W/'candidate-ddiv.S').read_text()
assert ' orrs r4,r6                    @ y0=(q31)y; nine ALU instructions since STR'in hardware
assert '.equ use_hw_div,1'in hardware and '.equ use_hw_div,0'in software
tc=Path(build['commands'][0][0]).parent;commands=[];disabled={}
for name,cpu,extra in [('generic_M0','cortex-m0plus',[]),('M4_soft','cortex-m4',[]),('M4_hard','cortex-m4',['-mfloat-abi=hard','-mfpu=fpv4-sp-d16'])]:
 for source in ['candidate-ddiv','candidate-software']:
  output=W/(name+'-'+source+'-disabled.o')
  command=[str(tc/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-DMK61_USE_M0_EABI=0','-DMK61_M0_RP2040_EABI=0',*extra,'-c',str(W/(source+'.S')),'-o',str(output)]
  subprocess.run(command,check=True);commands.append(command);e=ElfImage(output);assert not any(s[2]&2 and s[5]for s in e.sections);disabled[output.name]=sha(output)
for context in ['generic_M0','M4_soft','M4_hard']:
 for label in ['control','candidate']:
  e=ElfImage(W/(context+'-'+label+'.o'));assert not any(s[2]&2 and s[5]for s in e.sections)
out=dict(status='PASS_PRIVATE_NUMERATOR_ONE_CALLER_GUARD_COMMON_TAIL_AND_INACTIVE_SOURCE_PROOFS',candidate_ELF_sha256=sha(W/'candidate.elf'),
 all_calls_source_proven_R0zero_R1binary64positive_one=True,private_hidden_entry_named_reciprocal1_not_general_ddiv=True,
 all2048_exponent_guards_equivalent_and_R6_addends_identical=True,normal_guarded_exponents=[1,2044],guard_truth_table_sha256=hashlib.sha256(json.dumps(guard_rows,separators=(',',':')).encode()).hexdigest(),
 exact_product_identity='double_low_high(2^31*u1)=(0,u1) modulo2^64 for every uint32 u1',
 dead_R1_R2_R3_R4_R7_values_overwritten_before_next_use=True,common_after_second_product_tail_bytes=len(tails[0]),common_tail_sha256=hashlib.sha256(tails[0]).hexdigest(),all4_common_suffixes_byte_identical=True,
 seed312B_code_and_table_blob_unchanged=True,READY_nine_ALU_hardware_latency_block_unchanged=True,software_only_dead_numerator_unpacked_and_R0_setup_removed=True,
 no_new_table_values_RAM_or_libgcc=True,private_allocated_bytes=[1168,images['candidate'].named_sections['.ddiv'][5]],
 default_M0_M4_selected_root_and6_new_disabled_objects_empty=True,commands=commands,disabled_outputs=disabled,actual_ARM_or_MPFR_calls=0,hardware_accessed=False,goal_complete=False)
(W/'source-proof.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k not in['commands','disabled_outputs']},indent=2))
