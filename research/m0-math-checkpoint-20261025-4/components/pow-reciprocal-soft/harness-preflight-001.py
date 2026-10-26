"""Actual qualified boundary parent plus source-built reciprocal-call clone."""
from pathlib import Path
import importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];PARENT=ROOT/'.build/m0-pow-boundary128-20261025'
spec=importlib.util.spec_from_file_location('boundary128_parent_harness',PARENT/'harness.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
for n,v in vars(base).items():
 if not n.startswith('_'):globals()[n]=v
HERE=Path(__file__).resolve().parent;PARENT=ROOT/'.build/m0-pow-boundary128-20261025'
linked=json.loads((HERE/'build.json').read_bytes())
division_images={n:ElfImage(HERE/(n+'.elf'))for n in ['control','candidate']}
for n in division_images:assert sha(HERE/(n+'.elf'))==linked['images'][n]['ELF_sha256']
for e in division_images.values():
 s=e.named_sections['.ddiv']
 for image in base.resident_images+[base.boundary_images['candidate']]:
  assert not any(t[2]&2 and t[5] and max(s[3],t[3])<min(s[3]+s[5],t[3]+t[5])for t in image.named_sections.values())
def machine(label):
 if label=='Qfplib':return base.machine(label)
 m=base.machine('candidate')
 if label in division_images:
  e=division_images[label];e.load(m.uc)
  m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_ddiv_seed'))})
 return m
