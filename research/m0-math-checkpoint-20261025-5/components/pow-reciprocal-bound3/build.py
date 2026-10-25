"""Use the exact bounded seed correction in the private numerator-one path."""
from pathlib import Path
import difflib,hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-zero-20261025';U=ROOT/'.build/m0-ddiv-seed-bound3-20261025'
assert not(W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert json.loads((U/'unit-proof.json').read_bytes())['actual_ARM_calls']==2097152
for name in ['inline-seed-table.inc','candidate-remainder-certificate.inc','LICENSE.TXT']:(W/name).write_bytes((P/name).read_bytes())
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 for name in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:(d/name).write_bytes((P/'candidate'/name).read_bytes())
 (W/(label+'-inline-seed.inc')).write_bytes((U/(label+'-seed.inc')).read_bytes())
 (W/(label+'-ddiv.S')).write_bytes((P/'candidate-ddiv.S').read_bytes())
 sw=(P/'candidate-software.S').read_text();assert sw.count('#include "inline-seed.inc"')==1
 (W/('software.S'if label=='control'else'candidate-software.S')).write_text(sw.replace('#include "inline-seed.inc"','#include "'+label+'-inline-seed.inc"'))
 (W/(label+'-seed17.S')).write_bytes((P/'candidate-seed17.S').read_bytes())
 (W/(label+'.ld')).write_bytes((P/'candidate.ld').read_bytes())
(W/'bounded-seed.patch').write_text(''.join(difflib.unified_diff((W/'control-inline-seed.inc').read_text().splitlines(True),(W/'candidate-inline-seed.inc').read_text().splitlines(True),fromfile='parent/inline-seed.inc',tofile='candidate/inline-seed.inc')))
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
out=dict(status='BUILT_PRIVATE_BOUND3_SEED_NOT_QUALIFIED',images=meta,commands=commands,
 source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 root_call_relocation_offset=old['root_call_relocation_offset'],private_precondition=old['private_precondition'],
 control_all_allocated_bytes_addresses_equal_parent=True,all_other_resident_sections_bytes_addresses_unchanged=True,
 candidate_ddiv_size=images['candidate'].named_sections['.ddiv'][5],allocated_delta=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],
 shared_unit_macro_sha256=sha(W/'candidate-inline-seed.inc'),hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
