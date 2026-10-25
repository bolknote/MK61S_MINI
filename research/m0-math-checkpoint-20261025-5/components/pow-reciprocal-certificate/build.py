"""Exact remainder-sign certificate in the private positive-one reciprocal."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-inline-20261025'
assert not(W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
unit=ROOT/'.build/m0-ddiv-remainder-certificate-r2-20261025'
assert json.loads((unit/'unit-proof.json').read_bytes())['actual_ARM_calls']==201600
for name in ['inline-seed.inc','inline-seed-table.inc','LICENSE.TXT']:(W/name).write_bytes((P/name).read_bytes())
(W/'remainder-certificate.inc').write_bytes((unit/'remainder-certificate.inc').read_bytes())
oldblock=''' mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3  @ xL*zL
 negs r2,r2                    @ borrow from low half?
 sbcs r4,r3                    @ y-xz Q73 (remainder bits 52..73)

 cmp r4,#0

 bmi 1f
'''
patch=[]
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:(d/name).write_bytes((P/'candidate'/name).read_bytes())
 for kind,tag in [('hardware','mk61_m0_reciprocal1'),('software','mk61_m0_reciprocal1_sw')]:
  source=(P/('candidate-ddiv.S'if kind=='hardware'else'candidate-software.S')).read_text();before=source
  def marker(suffix):return '.global '+tag+suffix+'\n'+tag+suffix+':\n'
  shift=' lsls r4,#16                   @ Q105-32=Q73\n';assert source.count(shift)==1
  source=source.replace(shift,marker('_y_low_shift')+(shift if label=='control'else' // Private numerator one: yL is exactly zero; flags dead before SUBS.\n'))
  assert source.count(oldblock)==1
  replacement=(oldblock if label=='control'else' remainder_certificate .Lcertificate_full,.Lcertificate_down\n')
  source=source.replace(oldblock,marker('_certificate_begin')+replacement+marker('_certificate_up')+'.Lcertificate_up:\n')
  needle='1:\n lsrs r0,#1                    @ shift back down to Q52\n';assert source.count(needle)==1
  source=source.replace(needle,'1:\n'+marker('_certificate_down')+'.Lcertificate_down:\n lsrs r0,#1                    @ shift back down to Q52\n')
  if label=='candidate':
   size='.size '+('mk61_m0_reciprocal1'if kind=='hardware'else'mk61_m0_reciprocal1_sw_from_guard')+','
   pos=source.index(size)
   full=marker('_certificate_full')+'''.Lcertificate_full:
 adds r4,r5                   @ restore exact modular base before full product
 mul32_32_64 r2,r0, r2,r3, r5,r6,r7,r2,r3
 negs r2,r2
 sbcs r4,r3
 cmp r4,#0
 bmi .Lcertificate_down
 b .Lcertificate_up

'''
   source=source[:pos]+full+source[pos:]
   section='.section .m0_ddiv_hint_hw,'if kind=='hardware'else'.section .m0_ddiv_hint_sw,'
   assert source.count(section)==1
   source=source.replace(section,'#include "remainder-certificate.inc"\n'+section)
  filename=label+'-ddiv.S'if kind=='hardware'else'software.S'if label=='control'else'candidate-software.S'
  (W/filename).write_text(source)
  if label=='candidate':patch.append(''.join(difflib.unified_diff(before.splitlines(True),source.splitlines(True),fromfile='parent/'+kind+'.S',tofile='candidate/'+kind+'.S')))
 (W/(label+'-seed17.S')).write_bytes((P/'candidate-seed17.S').read_bytes())
 (W/(label+'.ld')).write_bytes((P/'candidate.ld').read_bytes())
(W/'remainder-certificate.patch').write_text(''.join(patch))
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
out=dict(status='BUILT_PRIVATE_EXACT_REMAINDER_CERTIFICATE_NOT_QUALIFIED',images=meta,commands=commands,
 source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 root_call_relocation_offset=old['root_call_relocation_offset'],private_precondition=old['private_precondition'],
 control_all_allocated_bytes_addresses_equal_parent=True,all_other_resident_sections_bytes_addresses_unchanged=True,
 candidate_ddiv_size=images['candidate'].named_sections['.ddiv'][5],allocated_delta=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],
 shared_unit_macro_sha256=sha(W/'remainder-certificate.inc'),hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
