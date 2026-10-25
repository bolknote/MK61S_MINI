"""Actual exact-square parent and a one-entry exact-boundary replacement."""
from pathlib import Path
import importlib.util,json,struct,sys
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];PARENT=ROOT/'.build/m0-pow-square128-r2-20261025'
sys.path.insert(0,str(PARENT))
spec=importlib.util.spec_from_file_location('square128_parent_harness',PARENT/'harness.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
for n,v in vars(base).items():
 if not n.startswith('_'):globals()[n]=v
HERE=Path(__file__).resolve().parent;PARENT=ROOT/'.build/m0-pow-square128-r2-20261025'
linked=json.loads((HERE/'build.json').read_bytes());boundary_images={n:ElfImage(HERE/(n+'.elf'))for n in ['control','candidate']}
for n in boundary_images:assert sha(HERE/(n+'.elf'))==linked['images'][n]['ELF_sha256']
resident_images=[ElfImage(ROOT/'.build/m0-asin-scaled-bound-v164-20261023/firmware/mk61s-picocalc-pico-h.elf')]
resident_images+=[ElfImage(ROOT/('.build/'+d+'/candidate.elf'))for d in ['m0-exp-cached-product-20261024','m0-pow-square-ordinary-20261024','m0-pow-rsqrt-asm-20261024','m0-pow-exp-table-product-20261025','m0-pow-square128-r2-20261025']]
section=boundary_images['candidate'].named_sections['.boundary128'];assert 0x10000000<=section[3] and section[3]+section[5]<=0x10200000
for image in resident_images:
 assert not any(s[2]&2 and s[5] and max(s[3],section[3])<min(s[3]+s[5],section[3]+section[5])for s in image.named_sections.values())
def machine(label):
 if label=='Qfplib':return base.square_machine(label)
 m=base.square_machine('candidate')
 if label in boundary_images:
  e=boundary_images[label];e.load(m.uc)
  m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith('mk61_m0_boundary128')})
 return m
def trace_boundaries(m,label):
 from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR
 entries=[];operands=[]
 image=boundary_images['candidate']
 address=image.symbols['mk61_m0_boundary128']&~1 if label=='candidate' else 0x10150000
 size=image.sizes['mk61_m0_boundary128'] if label=='candidate' else 532
 def entry(uc,pc,size,user):
  pointer=uc.reg_read(UC_ARM_REG_R0)
  entries.append(dict(power=bytes(uc.mem_read(pointer,24)).hex(),denominator=uc.reg_read(UC_ARM_REG_R1),
   inverse=uc.reg_read(UC_ARM_REG_R2),cell=f'{struct.unpack("<Q",uc.mem_read(uc.reg_read(UC_ARM_REG_SP),8))[0]:016X}'))
 m.uc.hook_add(UC_HOOK_CODE,entry,begin=address,end=address)
 for pc,kind in [(0x1014f720,'compare'),(0x100f9268,'multiply')]:
  def operand(uc,pc,unused,user,kind=kind):
   lr=uc.reg_read(UC_ARM_REG_LR)&~1
   if address<=lr<address+size:
    a=uc.reg_read(UC_ARM_REG_R0);b=uc.reg_read(UC_ARM_REG_R1)
    operands.append(dict(kind=kind,a=bytes(uc.mem_read(a,24)).hex(),b=bytes(uc.mem_read(b,24)).hex()))
  m.uc.hook_add(UC_HOOK_CODE,operand,begin=pc,end=pc)
 return entries,operands
