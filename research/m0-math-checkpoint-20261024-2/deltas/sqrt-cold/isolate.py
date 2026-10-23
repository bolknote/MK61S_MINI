"""Verify the two changed sqrt sections and exact relinked execution body."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023/source/code'
CC=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
commands=[]
def compile(src,out,cpu='cortex-m0plus',rp=True,use=True,hard=False):
 cmd=[str(CC/'arm-none-eabi-gcc'),'-mcpu='+cpu,'-mthumb','-mfloat-abi='+('hard' if hard else 'soft'),'-I',str(P)]
 if rp:cmd+=['-DMK61_M0_RP2040_EABI=1']
 if use:cmd+=['-DMK61_USE_M0_EABI=1']
 if hard:cmd+=['-mfpu=fpv4-sp-d16']
 cmd+=['-c',str(src),'-o',str(out)];subprocess.run(cmd,check=True);commands.append(cmd);return ElfImage(out)
def allocated(e):return {n:e.bytes_at(s) for n,s in e.named_sections.items() if s[2]&2 and s[1]!=8}
changes=[];objects={};normal_proof={}
for name,stem,section in [('native_eabi_m0.S','main','.m0_sqrt64_fixed.mk61_m0_sqrt'),('native_eabi_m0_rp2040.S','rp','.m0_sqrt_special')]:
 old=compile(P/name,W/('control-'+stem+'.o'));new=compile(W/name,W/('candidate-'+stem+'.o'))
 a,b=allocated(old),allocated(new);assert set(a)==set(b)
 assert [n for n in a if a[n]!=b[n]]==[section]
 assert sha(W/('candidate-'+stem+'.o'))==sha(W/(stem+'.o'))
 if stem=='main':
  table=old.symbols['pow_sqrt64_coefficients']
  assert table==new.symbols['pow_sqrt64_coefficients']==352
  assert a[section][table:]==b[section][table:]
  # Eight new cold-guard bytes consume eight old alignment NOP bytes.
  # Normal instructions/literals move by8; its sole ADR still targets
  # exactly the same coefficient address. Check that exception explicitly.
  assert a[section][table-8:table]==bytes.fromhex('c046')*4
  before=a[section][20:table-8];after=b[section][28:table]
  differences=[i for i in range(0,len(before),2) if before[i:i+2]!=after[i:i+2]]
  assert differences==[86-20],differences
  for body,start in ((before,20),(after,28)):
   offset=start+differences[0];instruction=int.from_bytes(body[differences[0]:differences[0]+2],'little')
   assert instruction&0xff00==0xa400
   assert ((offset+4)&~3)+4*(instruction&255)==table
  normal_proof=dict(normal_code_and_literals_shifted_bytes=8,
                    only_instruction_encoding_change='ADR R4 at old+0x56/new+0x5e; target+0x160 unchanged',
                    old_alignment_NOP_bytes_consumed=8,coefficient_table_offset_and_bytes_identical=True)
 changes.append(dict(section=section,before_bytes=len(a[section]),after_bytes=len(b[section]),delta=len(b[section])-len(a[section])))
 objects[stem]=new
old_special=(P/'native_eabi_m0_sqrt_special.S.inc').read_text()
new_special=(W/'native_eabi_m0_sqrt_special.S.inc').read_text()
assert old_special.split('.Lsqrt_special_subnormal:\n',1)[1]==new_special.split('.Lsqrt_special_subnormal:\n',1)[1]
cmd=[str(CC/'arm-none-eabi-ld'),'-T',str(W/'candidate.ld'),str(W/'candidate-main.o'),str(W/'candidate-rp.o'),'-o',str(W/'relinked.elf')]
subprocess.run(cmd,check=True);commands.append(cmd)
e=ElfImage(W/'candidate.elf')
relinked=ElfImage(W/'relinked.elf')
assert allocated(e)==allocated(relinked)
assert set(e.symbols)-set(relinked.symbols)=={'main.o'}
assert set(relinked.symbols)-set(e.symbols)=={'candidate-main.o'}
assert e.symbols['main.o']==relinked.symbols['candidate-main.o']==0
assert all(relinked.symbols[n]==v for n,v in e.symbols.items() if n in relinked.symbols)
assert {n for n in e.named_sections if e.bytes_at(e.named_sections[n])!=relinked.bytes_at(relinked.named_sections[n])}=={'.symtab','.strtab'}
assert e.symbols['mk61_m0_sqrt']==0x1016bb01 and e.symbols['mk61_m0_sqrt_special']==0x1016ba21
assert e.named_sections['.sqrt_special'][5]<=0xe0
assert e.named_sections['.sqrt'][5]<=0x4500
undefined=subprocess.check_output([str(CC/'arm-none-eabi-nm'),'-u',str(W/'candidate.elf')],text=True).splitlines();assert not undefined
assert not any(s[1] in (4,9) and s[5] for s in e.sections)
contexts=[]
for label,cpu,use,hard in [('generic_M0','cortex-m0plus',True,False),('M4_soft','cortex-m4',False,False),('M4_hard','cortex-m4',False,True)]:
 total=0
 for name,stem in [('native_eabi_m0.S','main'),('native_eabi_m0_rp2040.S','rp')]:
  old=compile(P/name,W/(label+'-'+stem+'-control.o'),cpu,False,use,hard)
  new=compile(W/name,W/(label+'-'+stem+'-candidate.o'),cpu,False,use,hard)
  assert allocated(old)==allocated(new),(label,stem);total+=sum(map(len,allocated(new).values()))
 contexts.append(dict(context=label,allocated_code_and_data_identical=True,allocated_bytes=total))
report=dict(status='PASS_ONLY_SQRT_GUARD_AND_COLD_CLASSIFICATION_CHANGED',changed_sections=changes,total_allocated_bytes_delta=sum(c['delta'] for c in changes),
            all_other_allocated_sections_identical=True,normal_body_equivalence=normal_proof,
            subnormal_scale_convert_root_source_suffix_identical=True,independent_public_objects_equal_original_link_inputs=True,
            independently_relinked_allocated_bytes_equal_executed_without_exclusions=True,
            relink_nonallocated_difference='Only .symtab/.strtab: input file main.o renamed candidate-main.o, value0; all common symbol addresses exact.',
            public_sqrt_and_cold_entry_addresses_unchanged=True,
            old_fixed_slots_fit=True,standalone_ELF_undefined_symbols=[],standalone_ELF_relocations=[],
            new_internal_branch_target='mk61_m0_sqrt_subnormal (alias in the existing cold helper)',new_libgcc_or_ROM_dependency=False,
            new_tables_or_global_RAM=False,contexts=contexts,candidate_ELF_sha256=sha(W/'candidate.elf'),
            source_files={n:sha(W/n) for n in ('native_eabi_m0.S','native_eabi_m0_sqrt_special.S.inc')},commands=commands,
            scope='Only three math sections linked for local execution, not a new production image or whole M4 rebuild.',canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
(W/'isolation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
