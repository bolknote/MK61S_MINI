"""Private 1/x specialization; no other ddiv caller or approximation changes."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-lut-20261025'
assert not(W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
product=' mul32_32_64 r4,r6, r4,r5, r2,r3,r7,r4,r5  @ y0*u1 Q61\n adds r4,r4\n adcs r5,r5                    @ a0=(q30)(y0*u1)'
mid=' ldr r4,[r13,#4]               @ xH'
patches=[]
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 (d/'native_eabi_m0_rp2040.S').write_bytes((P/'candidate/native_eabi_m0_rp2040.S').read_bytes())
 prefix=(P/'candidate/native_eabi_m0_pow_root_prefix.inc').read_text()
 if label=='candidate':
  assert prefix.count('\tbl\tmk61_m0_hint_ddiv\n')==1
  prefix=prefix.replace('\tbl\tmk61_m0_hint_ddiv\n','\tbl\tmk61_m0_reciprocal1\n')
 (d/'native_eabi_m0_pow_root_prefix.inc').write_text(prefix)
 (W/(label+'.ld')).write_bytes((P/'candidate.ld').read_bytes())
 hardware=(P/'candidate-ddiv.S').read_text();software=(P/'software.S').read_text()
 for kind,source in [('hardware',hardware),('software',software)]:
  assert source.count(product)==1 and source.count(mid)==1
  tag=('mk61_m0_hint'if kind=='hardware'else'mk61_m0_sw')if label=='control'else('mk61_m0_reciprocal1'if kind=='hardware'else'mk61_m0_reciprocal1_sw')
  first='.global '+tag+'_first_product\n'+tag+'_first_product:\n'
  after='.global '+tag+'_after_second_product\n'+tag+'_after_second_product:\n'
  source=source.replace(product,first+(product if label=='control'else' // Contract: numerator is exactly positive1; y0=2^31.\n mov r5,r6\n movs r4,#0'))
  source=source.replace(mid,after+mid)
  if label=='candidate':
   source=source.replace('mk61_m0_hint_ddiv','mk61_m0_reciprocal1').replace('mk61_m0_ddiv_sw_from_guard','mk61_m0_reciprocal1_sw_from_guard')
   source=source.replace('mk61_m0_hint_join','mk61_m0_reciprocal1_join').replace('mk61_m0_sw_join','mk61_m0_reciprocal1_sw_join')
   if kind=='software':
    unused=' movs r0,#0\n mvns r0,r0\n'
    assert source.count(unused)==1
    source=source.replace(unused,' // Seed takes D only; R0 is overwritten before use.\n')
    for dead in [' lsls r1,#12\n lsrs r1,#12\n orrs r1,r4                    @ normal dividend significand\n',' lsls r4,r1,#11\n lsrs r6,r0,#21\n orrs r4,r6                    @ y0=(q31)y; nine ALU instructions since STR\n']:
     assert source.count(dead)==1
     source=source.replace(dead,' // Numerator one needs no software unpacking; R1/R4 are dead.\n')
   else:
    guard=''' lsls r4, r1, #1
 lsrs r4, r4, #21
 lsls r5, r3, #1
 lsrs r5, r5, #21
 subs r6, r4, #1
 ldr r7, =2045
 cmp r6, r7
 bhi .Lrp2040_div_slow
 subs r6, r5, #1
 cmp r6, r7
 bhi .Lrp2040_div_slow
 subs r6, r4, r5
 lsrs r5,r7,#1
 subs r5,#1                    @ 1021
 adds r6,r5
 subs r7,#2                    @ 2043
 cmp r6, r7
 bhi .Lrp2040_div_slow
'''
    simpler=''' // Positive numerator1: accept exactly the old1<=E<=2044.
 lsls r5,r3,#1
 lsrs r5,#21
 subs r6,r5,#1
 ldr r7,=2043
 cmp r6,r7
 bhi .Lrp2040_div_slow
 subs r6,r7,r6                 @ 2044-E, same guarded exponent addend
'''
    assert source.count(guard)==1
    source=source.replace(guard,simpler)
  filename=(label+'-ddiv.S')if kind=='hardware'else('software.S'if label=='control'else'candidate-software.S')
  (W/filename).write_text(source)
  if label=='candidate':
   old=(P/('candidate-ddiv.S'if kind=='hardware'else'software.S')).read_text()
   patches.append(''.join(difflib.unified_diff(old.splitlines(True),source.splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S')))
 (W/(label+'-seed17.S')).write_bytes((P/'candidate-seed17.S').read_bytes())
(W/'reciprocal1.patch').write_text(''.join(patches));(W/'LICENSE.TXT').write_bytes((P/'LICENSE.TXT').read_bytes())
old=json.loads((P/'build.json').read_bytes());commands=[];remap=lambda s:s.replace(str(P)+'/',str(W)+'/')
def run(c):subprocess.run(c,cwd=W,check=True);commands.append(c)
for recorded in old['commands']:
 command=[remap(s)for s in recorded];output=Path(command[command.index('-o')+1]).name
 if output=='software.o':
  run(command)
  run([s.replace(str(W/'software.S'),str(W/'candidate-software.S')).replace(str(W/'software.o'),str(W/'candidate-software.o'))for s in command])
 elif output=='candidate.elf':
  run([s.replace(str(W/'software.o'),str(W/'candidate-software.o')).replace('mk61_m0_hint_ddiv','mk61_m0_reciprocal1')for s in command])
 else:run(command)
parent=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
assert alloc(images['control'])==alloc(parent)
assert {n for n in alloc(parent)if alloc(parent)[n]!=alloc(images['candidate'])[n]}=={'.ddiv'}
assert images['candidate'].symbols['mk61_m0_reciprocal1']==parent.symbols['mk61_m0_hint_ddiv']
meta={}
for label,e in images.items():
 entry='mk61_m0_hint_ddiv'if label=='control'else'mk61_m0_reciprocal1'
 software='mk61_m0_ddiv_sw_from_guard'if label=='control'else'mk61_m0_reciprocal1_sw_from_guard'
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),entry_symbol=entry,entry=e.symbols[entry],software_symbol=software,software=e.symbols[software],seed=e.symbols['mk61_m0_ddiv_seed17'],allocated={n:dict(address=s[3],bytes=s[5])for n,s in e.named_sections.items()if s[2]&2 and s[5]})
out=dict(status='BUILT_PRIVATE_RECIPROCAL1_EXACT_PRODUCT_NOT_QUALIFIED',images=meta,commands=commands,source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),root_call_relocation_offset=old['root_call_relocation_offset'],
 control_all_allocated_bytes_addresses_equal_parent=True,only_candidate_ddiv_section_changed=True,root_call_bytes_address_unchanged_but_private_symbol_renamed=True,
 private_candidate_precondition='R0=0,R1=0x3ff00000; denominator R2:R3 any binary64',
 seed_source_bytes_unchanged=True,normal_NR_exact_remainder_RNE_suffix_unchanged=True,
 private_allocated_code_delta=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
