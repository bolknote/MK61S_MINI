"""Actual square128 parent plus real linked conservative boundary filter."""
from pathlib import Path
import importlib.util,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
PARENT=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(PARENT))
spec=importlib.util.spec_from_file_location('square128_parent_harness',PARENT/'harness.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
for n,v in vars(base).items():
 if not n.startswith('_'):globals()[n]=v
HERE=Path(__file__).resolve().parent;PARENT=ROOT/'.build/m0-pow-square128-r2-20261025'
linked=json.loads((HERE/'public-build.json').read_bytes())
boundary_images={n:ElfImage(HERE/(n+'.elf'))for n in ['control','candidate']}
for n in boundary_images:assert sha(HERE/(n+'.elf'))==linked['images'][n]['ELF_sha256']
resident_images=[ElfImage(ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')]
resident_images+=[ElfImage(ROOT/('.build/'+d+'/candidate.elf'))for d in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025']]
for n,s in boundary_images['candidate'].named_sections.items():
 if not (s[2]&2 and s[5])or n=='.front':continue
 assert 0x10000000<=s[3] and s[3]+s[5]<=0x10200000
 for image in resident_images:
  assert not any(t[2]&2 and t[5] and max(s[3],t[3])<min(s[3]+s[5],t[3]+t[5])for t in image.named_sections.values()),(n,hex(s[3]))
def machine(label):
 if label=='Qfplib':return base.square_machine(label)
 m=base.square_machine('candidate')
 if label in boundary_images:
  image=boundary_images[label];image.load(m.uc)
  m.elf.symbols.update({n:a for n,a in image.symbols.items()if n.startswith('mk61_m0_bound80_')})
 return m

def trace_boundaries(m,label):
 from unicorn.arm_const import UC_ARM_REG_SP
 entries=[];fallback=[]
 image=boundary_images['candidate']
 address=image.symbols['mk61_m0_bound80_filter']&~1 if label=='candidate' else 0x10150000
 def entry(uc,pc,size,user):
  pointer=uc.reg_read(UC_ARM_REG_R0)
  entries.append(dict(power=bytes(uc.mem_read(pointer,24)).hex(),denominator=uc.reg_read(UC_ARM_REG_R1),
                      inverse=uc.reg_read(UC_ARM_REG_R2),cell=f'{struct.unpack("<Q",uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8))[0]:016X}'))
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
 if label=='candidate':
  address=image.symbols['mk61_m0_bound80_old_boundary']&~1
  def old(uc,pc,size,user):fallback.append(1)
  m.uc.hook_add(UC_HOOK_CODE,old,begin=address,end=address)
 return entries,fallback
