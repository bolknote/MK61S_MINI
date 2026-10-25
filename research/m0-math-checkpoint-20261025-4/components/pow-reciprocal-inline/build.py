"""Inline the exact private seed and add the proved tiny-denominator endpoint."""
from pathlib import Path
import difflib,hashlib,json,re,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-one-20261025'
assert not(W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
seed=(P/'candidate-seed17.S').read_text();table=seed[seed.index(' .hword '):seed.index('#endif')]
# The fold/Newton estimate is unchanged. Its proved[-1,3] quotient error
# permits one upward step; all downward steps preserve the exact residual.
macro='''.macro reciprocal_seed_inline
.global mk61_m0_inline_seed_begin
mk61_m0_inline_seed_begin:
 lsrs r6,r1,#9
 subs r6,#128
 lsls r6,#1
 adr r4,.Linline_seed_table
 ldrh r6,[r4,r6]
 adds r4,r1,#1
 lsrs r4,#1
 muls r4,r6
 lsls r4,#1
 asrs r4,#17
 muls r4,r6
 asrs r4,#15
 subs r6,r4
 movs r7,r6
 muls r7,r1
 mvns r7,r7
 bmi .Linline_seed_high
 cmp r7,r1
 bcc .Linline_seed_done
 adds r6,#1
 subs r7,r1
 b .Linline_seed_done
.Linline_seed_high:
 subs r6,#1
 adds r7,r1
 bmi .Linline_seed_high
.Linline_seed_done:
.global mk61_m0_inline_seed_done
mk61_m0_inline_seed_done:
.endm
'''
(W/'inline-seed.inc').write_text(macro)
(W/'inline-seed-table.inc').write_text('.p2align 2\n.Linline_seed_table:\n'+table)
cold='''// Called only with the existing20B saved frame and raw positive-one args.
.Lreciprocal1_special:
 cmp r5,#0
 bne .Lrp2040_div_slow
 lsls r7,r3,#1
 lsrs r7,#1
 movs r6,#1
 lsls r6,#18
 cmp r7,r6
 bhi .Lrp2040_div_slow
 bne .Lreciprocal1_overflow
 cmp r2,#0
 bne .Lrp2040_div_slow
.Lreciprocal1_overflow:
 movs r0,#0
 lsrs r1,r3,#31
 lsls r1,#31
 ldr r7,=0x7ff00000
 orrs r1,r7
 pop {r4-r7,pc}
'''
patch=[]
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:(d/name).write_bytes((P/'candidate'/name).read_bytes())
 for kind in ['hardware','software']:
  source=(P/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text();before=source
  if label=='candidate':
   general=' mov r7,r1\n eors r7,r3\n lsrs r7,#31                  @ result sign\n'
   assert source.count(general)==1
   source=source.replace(general,' lsrs r7,r3,#31               @ positive numerator: sign is divisor sign\n')
   if kind=='hardware':
    small=' mov r6,r1\n eors r6,r3\n lsrs r6,#31\n';assert source.count(small)==1
    source=source.replace(small,' lsrs r6,r3,#31\n')
    guard=' cmp r6,r7\n bhi .Lrp2040_div_slow\n';assert source.count(guard)==1
    source=source.replace(guard,' cmp r6,r7\n bhi .Lreciprocal1_special\n')
    source=source.replace('.Lrp2040_div_slow:',cold+'\n.Lrp2040_div_slow:')
   else:
    source=source.replace('.section .m0_ddiv_hint_sw,','#include "inline-seed.inc"\n.section .m0_ddiv_hint_sw,')
    start=source.index(' push {r0-r3,r7}');end=source.index(' pop {r0-r3,r7}',start)+len(' pop {r0-r3,r7}')
    source=source[:start]+''' lsrs r1,r3,#4                 @ D17; R0/R2/R3/R5/R12 stay live
 reciprocal_seed_inline
 adds r6,#1
 lsrs r6,#1
'''+source[end:]
    source=source.replace('.ltorg\n','.ltorg\n#include "inline-seed-table.inc"\n')
  filename=(label+'-ddiv.S')if kind=='hardware'else('software.S'if label=='control'else'candidate-software.S')
  (W/filename).write_text(source)
  if label=='candidate':patch.append(''.join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S')))
 (W/(label+'-seed17.S')).write_bytes((P/'candidate-seed17.S').read_bytes())
 script=(P/(label+'.ld')).read_text()
 if label=='candidate':script=script.replace(' KEEP(*(.m0_ddiv_seed17))','')
 (W/(label+'.ld')).write_text(script)
(W/'inline-and-overflow.patch').write_text(''.join(patch));(W/'LICENSE.TXT').write_bytes((P/'LICENSE.TXT').read_bytes())
old=json.loads((P/'build.json').read_bytes());commands=[];remap=lambda s:s.replace(str(P)+'/',str(W)+'/')
for recorded in old['commands']:
 c=[remap(s)for s in recorded];subprocess.run(c,cwd=W,check=True);commands.append(c)
parent=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
assert alloc(images['control'])==alloc(parent)
assert {n for n in alloc(parent)if alloc(parent)[n]!=alloc(images['candidate'])[n]}<={'.ddiv','.rootprefix'}
assert 'mk61_m0_ddiv_seed17'not in images['candidate'].symbols
meta={}
for label,e in images.items():
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),entry_symbol='mk61_m0_reciprocal1',entry=e.symbols['mk61_m0_reciprocal1'],software_symbol='mk61_m0_reciprocal1_sw_from_guard',software=e.symbols['mk61_m0_reciprocal1_sw_from_guard'],
  seed_symbol='mk61_m0_ddiv_seed17'if label=='control'else'mk61_m0_inline_seed_begin',seed=e.symbols['mk61_m0_ddiv_seed17'if label=='control'else'mk61_m0_inline_seed_begin'],
  allocated={n:dict(address=s[3],bytes=s[5])for n,s in e.named_sections.items()if s[2]&2 and s[5]})
out=dict(status='BUILT_PRIVATE_INLINE_EXACT_SEED_AND_TINY_OVERFLOW_NOT_QUALIFIED',images=meta,commands=commands,source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 root_call_relocation_offset=old['root_call_relocation_offset'],private_precondition=old['private_candidate_precondition'],control_all_allocated_bytes_addresses_equal_parent=True,
 candidate_ddiv_size=images['candidate'].named_sections['.ddiv'][5],allocated_delta=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],
 unchanged256B_seed_table_and_exact_integer_quotient=True,standalone_seed_not_allocated_in_candidate=True,hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
