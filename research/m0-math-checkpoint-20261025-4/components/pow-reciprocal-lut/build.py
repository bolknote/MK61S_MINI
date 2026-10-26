"""Relink a source-derived control/candidate changing only the private seed."""
from pathlib import Path
import hashlib,json,subprocess,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1];P=ROOT/'.build/m0-pow-reciprocal-soft-20261025';SEED=ROOT/'.build/m0-ddiv-seed-lut-20261025'
assert not (W/'FROZEN.json').exists()
sys.path.insert(0,str(ROOT/'tests'));from check_stm32_vectors import ElfImage
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
selected=json.loads((SEED/'selection.json').read_bytes());name=selected['selected'];assert name=='lut128_floor'
for label in ['control','candidate']:
 d=W/label;d.mkdir(exist_ok=True)
 for source in ['native_eabi_m0_rp2040.S','native_eabi_m0_pow_root_prefix.inc']:(d/source).write_bytes((P/'candidate'/source).read_bytes())
 (W/(label+'-ddiv.S')).write_bytes((P/'candidate-ddiv.S').read_bytes())
 (W/(label+'.ld')).write_bytes((P/'candidate.ld').read_bytes())
for source in ['software.S','LICENSE.TXT']:(W/source).write_bytes((P/source).read_bytes())
(W/'control-seed17.S').write_bytes((P/'seed17.S').read_bytes())
(W/'candidate-seed17.S').write_bytes((SEED/(name+'.S')).read_bytes())
old=json.loads((P/'build.json').read_bytes());commands=[]
def run(command):subprocess.run(command,cwd=W,check=True);commands.append(command)
remap=lambda s:s.replace(str(P)+'/',str(W)+'/')
for recorded in old['commands']:
 command=[remap(s)for s in recorded]
 output=Path(command[command.index('-o')+1]).name
 if output=='seed17.o':
  for label in ['control','candidate']:
   c=[s.replace(str(W/'seed17.S'),str(W/(label+'-seed17.S'))).replace(str(W/'seed17.o'),str(W/(label+'-seed17.o')))for s in command]
   run(c)
 elif output in ['control.elf','candidate.elf']:
  label=output[:-4]
  command=[s.replace(str(W/'seed17.o'),str(W/(label+'-seed17.o')))for s in command]
  run(command)
 else:run(command)
parent=ElfImage(P/'candidate.elf');images={n:ElfImage(W/(n+'.elf'))for n in ['control','candidate']}
def alloc(e):return {n:(s[1],s[2],s[3],s[5],None if s[1]==8 else e.bytes_at(s))for n,s in e.named_sections.items()if s[2]&2 and s[5]}
assert alloc(images['control'])==alloc(parent)
assert {n for n in alloc(parent)if alloc(parent)[n]!=alloc(images['candidate'])[n]}=={'.ddiv'}
for label,e in images.items():
 for symbol in ['mk61_m0_hint_ddiv','mk61_m0_hint_join','mk61_m0_ddiv_sw_from_guard','mk61_m0_sw_join']:
  assert e.symbols[symbol]==parent.symbols[symbol],symbol
meta={n:dict(ELF_sha256=sha(W/(n+'.elf')),entry=e.symbols['mk61_m0_hint_ddiv'],software=e.symbols['mk61_m0_ddiv_sw_from_guard'],seed=e.symbols['mk61_m0_ddiv_seed17'],allocated={n:dict(address=s[3],bytes=s[5])for n,s in e.named_sections.items()if s[2]&2 and s[5]})for n,e in images.items()}
out=dict(status='BUILT_PRIVATE_EXACT_SMALL_TABLE_SEED_ONLY_NOT_QUALIFIED',images=meta,commands=commands,source_parent=str(P.relative_to(ROOT)),source_parent_FROZEN_sha256=sha(P/'FROZEN.json'),
 root_call_relocation_offset=old['root_call_relocation_offset'],control_all_allocated_bytes_addresses_equal_parent=True,
 only_candidate_ddiv_section_changed=True,selected_seed=name,selection_sha256=sha(SEED/'selection.json'),bare_unit_proof_sha256=sha(SEED/'unit-proof.json'),
 table_bytes=256,seed_function_bytes=images['candidate'].sizes['mk61_m0_ddiv_seed17'],
 new_allocated_code_bytes=images['candidate'].named_sections['.ddiv'][5]-parent.named_sections['.ddiv'][5],hardware_accessed=False)
(W/'build.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items()if k!='commands'},indent=2))
