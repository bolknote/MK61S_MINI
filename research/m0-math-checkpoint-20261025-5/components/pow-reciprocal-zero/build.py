"""Preserve known zero through refinement and the exact remainder certificate."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-certificate-20261025';U=ROOT/'.build/m0-ddiv-remainder-certificate-r3-20261025'
assert not(W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert json.loads((U/'unit-proof.json').read_bytes())['actual_ARM_calls']==201600
for name in ['inline-seed.inc','inline-seed-table.inc','LICENSE.TXT']:(W/name).write_bytes((P/name).read_bytes())
patch=[]
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:(d/name).write_bytes((P/'candidate'/name).read_bytes())
 macro=(P/'remainder-certificate.inc')if label=='control'else(U/'remainder-certificate.inc')
 (W/(label+'-remainder-certificate.inc')).write_bytes(macro.read_bytes())
 for kind,tag in [('hardware','mk61_m0_reciprocal1'),('software','mk61_m0_reciprocal1_sw')]:
  source=(P/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text();before=source
  source=source.replace('#include "remainder-certificate.inc"','#include "'+label+'-remainder-certificate.inc"')
  def marker(suffix):return '.global '+tag+suffix+'\n'+tag+suffix+':\n'
  old=' mul32_32_64 r2,r5, r2,r3, r1,r4,r7,r2,r3  @ xL*a0\n';assert source.count(old)==1
  source=source.replace(old,marker('_before_second_product')+(old if label=='control'else' mul32_32_64 r2,r5, r2,r3, r1,r0,r7,r2,r3  @ xL*a0; preserve R4=0\n'))
  needle=' subs r0,r4,r2                 @ r0x=y-x*a0 Q57 (signed)\n';assert source.count(needle)==1
  source=source.replace(needle,needle+marker('_after_y_residual'))
  half=' lsls r4,#1                    @ y now Q58\n';assert source.count(half)==1
  source=source.replace(half,marker('_half_normalization')+(half if label=='control'else' // R4 is already zero; next shifts replace flags.\n'))
  source=source.replace('dd_2:\n','dd_2:\n'+marker('_pack_begin'))
  if label=='candidate':
   changes=[(' ldr r4,[r13,#4]               @ xH\n muls r4,r5                    @ xH*a0\n adds r3,r4                    @ r2:r3 now x*a0 Q82\n',
             ' ldr r1,[r13,#4]               @ xH; R1 is dead temporary\n muls r1,r5                    @ xH*a0\n adds r3,r1                    @ r2:r3 now x*a0 Q82\n'),
            (' lsls r4,r0,#5                 @ y Q57\n',' // R4=0 survives the second product and xH temporary.\n'),
            (' movs r2,#0                    @ round up\n adds r0,#1\n adcs r1,r2\n',' adds r0,#1                    @ round up with known-zero R6\n adcs r1,r6\n'),
            (' bmi .Lcertificate_down\n b .Lcertificate_up\n',' bmi .Lcertificate_down\n movs r6,#0                   @ full multiplication clobbered R6\n b .Lcertificate_up\n')]
   for old,new in changes:assert source.count(old)==1,(kind,old);source=source.replace(old,new)
  filename=label+'-ddiv.S'if kind=='hardware'else'software.S'if label=='control'else'candidate-software.S'
  (W/filename).write_text(source)
  if label=='candidate':patch.append(''.join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S')))
 (W/(label+'-seed17.S')).write_bytes((P/'candidate-seed17.S').read_bytes())
 (W/(label+'.ld')).write_bytes((P/'candidate.ld').read_bytes())
(W/'known-zero.patch').write_text(''.join(patch))
old=json.loads((P/'build.json').read_bytes());commands=[];remap=lambda s:s.replace(str(P)+'/',str(W)+'/')
for recorded in old['commands']:
 c=[remap(s)for s in recorded];subprocess.run(c,cwd=W,check=True);commands.append(c)
parent=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
assert alloc(images['control'])==alloc(parent)
assert {n for n in alloc(parent)if alloc(parent)[n]!=alloc(images['candidate'])[n]}=={'.ddiv'}
meta={}
for label,e in images.items():
 assert 'mk61_m0_ddiv_seed17'not in e.symbols
 meta[label]=dict(ELF_sha256=sha(W/(label+'.elf')),entry_symbol='mk61_m0_reciprocal1',entry=e.symbols['mk61_m0_reciprocal1'],
  software_symbol='mk61_m0_reciprocal1_sw_from_guard',software=e.symbols['mk61_m0_reciprocal1_sw_from_guard'],
  seed_symbol='mk61_m0_inline_seed_begin',seed=e.symbols['mk61_m0_inline_seed_begin'],
  allocated={n:dict(address=s[3],bytes=s[5])for n,s in e.named_sections.items()if s[2]&2 and s[5]})
out=dict(status='BUILT_PRIVATE_KNOWN_ZERO_REFINEMENT_NOT_QUALIFIED',images=meta,commands=commands,
 source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 root_call_relocation_offset=old['root_call_relocation_offset'],private_precondition=old['private_precondition'],
 control_all_allocated_bytes_addresses_equal_parent=True,all_other_resident_sections_bytes_addresses_unchanged=True,
 candidate_ddiv_size=images['candidate'].named_sections['.ddiv'][5],allocated_delta=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],
 shared_unit_macro_sha256=sha(W/'candidate-remainder-certificate.inc'),hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
