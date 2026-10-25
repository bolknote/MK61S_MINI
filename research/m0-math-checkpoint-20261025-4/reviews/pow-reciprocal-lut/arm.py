"""Bounded actual LUT leaf and fresh private R3 save/restore qualification."""
import ast,hashlib,json,random,struct,sys
from collections import Counter
from pathlib import Path
sys.dont_write_bytecode=True
R=Path('/Users/bolk/Projects/MK61S_MINI');O=Path(__file__).resolve().parent;W=R/'.build/m0-pow-reciprocal-lut-20261025';P=R/'.build/m0-pow-reciprocal-soft-20261025'
SUP=R/'.build/m0-float-fma-qualification-20261023/support';sys.path[:0]=[str(SUP),str(R/'tests')]
from native_eabi_m0_arm_self_test import Machine,SP,bits
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ
from unicorn.arm_const import UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R12,UC_ARM_REG_SP,UC_ARM_REG_LR,UC_ARM_REG_PC,UC_ARM_REG_XPSR
REGS=[UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3];JOINREGS=[*REGS,UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R12,UC_ARM_REG_SP]
def ref(p):
 p=Path(p);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def save(n,d):
 with (O/n).open('x')as f:json.dump(d,f,indent=2);f.write('\n')
 print(json.dumps(ref(O/n)),flush=True)
def memory(e,a,n):
 s=next(s for s in e.sections if s[1]!=8 and s[3]<=a and a+n<=s[3]+s[5]);return e.bytes_at(s)[a-s[3]:a-s[3]+n]
def equal(a,b):return bool((a&0x7fffffffffffffff)>0x7ff0000000000000 and a&(1<<51))if (b&0x7fffffffffffffff)>0x7ff0000000000000 else a==b
states=dict(READY=struct.pack('<7I',0,0,0,0,0,0,1),DIRTY=struct.pack('<7I',17,3,17,3,5,2,3))
def seed():
 machines=dict(control=Machine(R/'.build/m0-pow-reciprocal-soft-independent-20261025/seed-only.elf',True),candidate=Machine(O/'seed-only.elf',True))
 active={};reads=[];rows=[];rng=random.Random(0x1281A025)
 for label,m in machines.items():
  assert not m.rom_models and not m.rom_initializers
  entry=m.elf.symbols['mk61_m0_ddiv_seed17']&~1;length=194 if label=='control'else 56;table=entry+56
  def code(uc,pc,n,user,entry=entry,length=length):
   assert entry<=pc and pc+n<=entry+length
   if pc==entry:
    uc.reg_write(UC_ARM_REG_XPSR,0x01000000|(active['flags']<<28));uc.reg_write(UC_ARM_REG_R12,active['r12']);uc.reg_write(UC_ARM_REG_R3,0xba025128)
  def write(*args):raise AssertionError('leaf writes no memory')
  def read(uc,access,a,n,v,user,label=label,table=table):
   assert label=='candidate'and a==table+2*((active['D']>>9)-128)and n==2
   reads.append(a)
  m.uc.hook_add(UC_HOOK_CODE,code);m.uc.hook_add(UC_HOOK_MEM_WRITE,write);m.uc.hook_add(UC_HOOK_MEM_READ,read)
 jobs=[]
 for i in [0,1,2,31,63,64,126,127]:
  for off in [0,1,510,511]:
   for flags in range(16):jobs.append((65536+512*i+off,flags,'table_boundary_all16flags'))
 for why,D in json.loads((O/'adversarial-D.json').read_text())['values'].items():jobs.append((D,len(jobs)&15,why))
 costs=json.loads((O/'full-domain-unit-costs.json').read_text())['costs']
 for D,flags,group in jobs:
  active.update(D=D,flags=flags,r12=rng.getrandbits(32));out={};counts={}
  for label,m in machines.items():
   reads.clear();got,_,cost=m.call('mk61_m0_ddiv_seed17',rng.getrandbits(32),D,width=32,count=True);q=got&0xffffffff;assert q==0xffffffff//D
   assert m.uc.reg_read(UC_ARM_REG_R1)==D and m.uc.reg_read(UC_ARM_REG_R12)==active['r12']
   if label=='candidate':assert m.uc.reg_read(UC_ARM_REG_R3)==0xffffffff%D and len(reads)==1
   else:assert m.uc.reg_read(UC_ARM_REG_R3)==0xba025128 and not reads
   counts[label]=cost;out[label]=q
  assert [counts['control'],counts['candidate']]==costs[str(D)]
  rows.append(dict(D=D,flags=flags,group=group,quotient=out['candidate'],candidate_R3_remainder=0xffffffff%D,instructions=counts))
 save('seed-arm.json',dict(status='PASS_BOUNDED_ACTUAL_LUT_SEED_EXACT_QUOTIENT_REMAINDER_AND_TABLE_READS',pairs=len(jobs),actual_ARM_calls=2*len(jobs),
  candidate_R3_is_clobbered_to_exact_remainder_not_preserved=True,R1_R12_PCS_SP_PC_preserved=True,
  all16NZCV_each32_bin_edges_plus_domain_adversaries=True,actual_PC56_excludes_table256=True,one_bounded_aligned_LDRH_per_call_no_writes=True,
  table_generation_bound=True,all_actual_costs_match_full_saved_domain_measurements=True,no_firmware_ROM_or_models=True,rows=rows,device_IO=0))
def load_machines():
 table=R/'.build/m0-pow-exp-table-product-20261025';im=ElfImage(table/'candidate.elf');entry=im.symbols['mk61_m0_pow_exp_table_product']&~1
 tree=ast.parse((R/'.build/m0-pow-exp-table-product-independent-20261025/arm.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='machine')
 env=dict(R=R,W=table,im=im,entry=entry,Machine=Machine,ElfImage=ElfImage,memory=memory)
 exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-table-loader>','exec'),env)
 machines={}
 for label in ['parent','control','candidate','Qfplib']:
  m=env['machine']('Qfplib'if label=='Qfplib'else'candidate')
  if label!='Qfplib':
   for folder in ['m0-pow-square128-r2-20261025','m0-pow-boundary128-20261025']:ElfImage(R/'.build'/folder/'candidate.elf').load(m.uc)
   e=ElfImage(P/'candidate.elf'if label=='parent'else O/'rebuild'/(label+'.elf'));e.load(m.uc)
   m.elf.symbols.update({n:a for n,a in e.symbols.items()if n.startswith(('mk61_m0_hint','mk61_m0_ddiv_sw','mk61_m0_ddiv_seed'))})
   assert m.elf.symbols['mk61_m0_hint_ddiv']==0x101e1041 and bytes(m.uc.mem_read(entry,20))==memory(im,entry,20)
  machines[label]=m
 return machines
# Reuse exact accepted guard/frame/MMIO audit source, then add a fresh R3
# leaf-return/pop/join proof. The old seed's R3-preservation is not inherited.
PREV=R/'.build/m0-pow-reciprocal-soft-independent-20261025/arm.py';tree=ast.parse(PREV.read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='audit')
exec(compile(ast.Module(body=[fn],type_ignores=[]),'<accepted-guard-frame-audit>','exec'),globals());base_audit=audit
def audit(m,label,active):
 out,baseclear=base_audit(m,label,active);current={};e=ElfImage(O/'rebuild'/(label+'.elf'));seed=e.symbols['mk61_m0_ddiv_seed17']&~1;join=e.symbols['mk61_m0_sw_join']&~1
 def code(uc,pc,n,user):
  if label!='candidate':return
  if pc==seed:
   sp=uc.reg_read(UC_ARM_REG_SP);current.update(ret=uc.reg_read(UC_ARM_REG_LR)&~1,saved_R3=struct.unpack('<I',uc.mem_read(sp+12,4))[0],D=uc.reg_read(UC_ARM_REG_R1))
  if current and pc==current['ret']:
   r3=uc.reg_read(UC_ARM_REG_R3);assert r3==0xffffffff%current['D']and r3!=current['saved_R3'];current['leaf_R3']=r3
  if pc==join and current:
   assert 'leaf_R3'in current and uc.reg_read(UC_ARM_REG_R3)==current['saved_R3']
   out['R3_save_clobber_pop_join'].append(dict(D=current['D'],saved_R3=current['saved_R3'],leaf_R3=current['leaf_R3'],join_R3=uc.reg_read(UC_ARM_REG_R3)))
 m.uc.hook_add(UC_HOOK_CODE,code)
 def clear():baseclear();out['R3_save_clobber_pop_join']=[];current.clear()
 clear();return out,clear
# Reuse bounded already-reviewed direct/public driver structure with two
# explicit adaptations: immediate soft parent uses its private alias, and
# this child has nine strict fixes. No frozen compound harness is imported.
class Adapt(ast.NodeTransformer):
 def __init__(self,name):self.name=name;self.edits=[]
 def visit_Constant(self,n):
  if self.name=='ddiv'and n.value=='__aeabi_ddiv':self.edits.append('parent entry __aeabi_ddiv -> mk61_m0_hint_ddiv');return ast.copy_location(ast.Constant('mk61_m0_hint_ddiv'),n)
  if self.name=='public'and n.value==48:self.edits.append('fixed count48 ->9');return ast.copy_location(ast.Constant(9),n)
  if self.name=='public'and isinstance(n.value,str)and'48'in n.value:self.edits.append('report48 ->9');return ast.copy_location(ast.Constant(n.value.replace('48','9')),n)
  return n
adapted=[]
for name in ['ddiv','public']:
 fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name);a=Adapt(name);fn=a.visit(fn)
 exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),'<bounded-driver-explicit-adaptation>','exec'),globals());adapted.append(dict(function=name,edits=a.edits))
if __name__=='__main__':
 assert len(sys.argv)==2 and sys.argv[1]in ['seed','ddiv','public'];globals()[sys.argv[1]]()
