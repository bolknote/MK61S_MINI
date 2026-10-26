"""Fresh private source images on the same resident runtime chain."""
from pathlib import Path
import importlib.util,json,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];PARENT=ROOT/'.build/m0-pow-reciprocal-zero-20261025'
spec=importlib.util.spec_from_file_location('zero_parent_harness',PARENT/'harness.py')
_parent_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(_parent_module)
for n,v in vars(_parent_module).items():
 if not n.startswith('_'):globals()[n]=v
HERE=Path(__file__).resolve().parent;PARENT=ROOT/'.build/m0-pow-reciprocal-zero-20261025'
linked=json.loads((HERE/'build.json').read_bytes());division_images={n:ElfImage(HERE/(n+'.elf'))for n in ['control','candidate']}
for n,e in division_images.items():assert sha(HERE/(n+'.elf'))==linked['images'][n]['ELF_sha256']
def machine(label):
 if label=='Qfplib':return _parent_module.machine(label)
 if label=='parent':return _parent_module.machine('candidate')
 m=_parent_module._parent_module._parent_module._one_parent._lut_parent._reciprocal_parent.machine('parent')
 e=division_images[label];e.load(m.uc)
 m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_sw_','mk61_m0_reciprocal1','mk61_m0_inline_seed'))})
 return m
