"""The source-built seed replacement over the exact same boundary/runtime chain."""
from pathlib import Path
import importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];PARENT=ROOT/'.build/m0-pow-reciprocal-soft-20261025'
spec=importlib.util.spec_from_file_location('reciprocal_soft_parent_harness',PARENT/'harness.py')
_reciprocal_parent=importlib.util.module_from_spec(spec);spec.loader.exec_module(_reciprocal_parent)
for n,v in vars(_reciprocal_parent).items():
 if not n.startswith('_'):globals()[n]=v
HERE=Path(__file__).resolve().parent;PARENT=ROOT/'.build/m0-pow-reciprocal-soft-20261025'
linked=json.loads((HERE/'build.json').read_bytes());division_images={n:ElfImage(HERE/(n+'.elf'))for n in ['control','candidate']}
for n,e in division_images.items():assert sha(HERE/(n+'.elf'))==linked['images'][n]['ELF_sha256']
for e in division_images.values():
 s=e.named_sections['.ddiv']
 for image in _reciprocal_parent._boundary_parent.resident_images+[_reciprocal_parent._boundary_parent.boundary_images['candidate']]:
  assert not any(t[2]&2 and t[5]and max(t[3],s[3])<min(t[3]+t[5],s[3]+s[5])for t in image.named_sections.values())
def machine(label):
 if label=='Qfplib':return _reciprocal_parent.machine(label)
 if label=='parent':return _reciprocal_parent.machine('candidate')
 # Start from the boundary parent so shorter components cannot inherit
 # executable trailing bytes from an older private division overlay.
 m=_reciprocal_parent.machine('parent');e=division_images[label];e.load(m.uc)
 m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_ddiv_seed'))})
 return m
