"""Small actual-ARM probe of rebuilt control and new public atan."""
from pathlib import Path
import hashlib,json,struct,sys
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine
from check_stm32_vectors import ElfImage
from m0_mpfr_oracle import Oracle,bits
from oracles import equal
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
build=json.loads((W/'candidate-build.json').read_text())
assert hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest()==build['ELF_sha256']
assert hashlib.sha256((W/'native_eabi_m0_atan_fast.inc').read_bytes()).hexdigest()==build['source_include_sha256'],'Compile current source before probing'
machines={'resident':Machine(ELF,True,bootrom=ROM),'Qfplib':Machine(REF,True)}
for label in ('parent','candidate'):
 m=Machine(ELF,True,bootrom=ROM);e=ElfImage(W/(('control' if label=='parent' else label)+'.elf'));e.load(m.uc)
 m.elf.symbols[label+'_atan']=e.symbols['mk61_m0_atan'];machines[label]=m
inputs=[int(r['x'],16) for r in json.loads((P/'slower-inputs.json').read_text())['rows'] if r['operation']=='atan']
inputs += [v^(1<<63) for v in inputs]
inputs += [int(v,16) for v in ('3FD3000000000003','BFD3000000000003','BFDB600000000000','3FDB600000000000','3F9BDA3A23F63D6A','BF9BDA3A23F63D6A')]
inputs += [int(v,16) for v in ('3FE5D1004FC925B6','BFE5D1004FC925B6','3FECB99548F4FA32','BFECB99548F4FA32')]
inputs += [bits(v) for v in (0.,-0.,1/64,1/32,0.1,0.25,0.5,1.,2.,4.,64.,128.,1e100)]
inputs += [int(r['x'],16) for r in json.loads((ROOT/'.build/m0-atan-residual-geometry-20261024/remaining-slower.json').read_text())['rows'] if r['SIO']=='READY']
inputs=list(dict.fromkeys(inputs))
o=Oracle();rows=[]
for raw in inputs:
 state=struct.pack('<7I',17,3,17,3,5,2,3);expected=o.reference('atan',raw);outputs={};counts={}
 for label,m in machines.items():
  m.uc.mem_write(0xd0000060,state)
  name='mk61_m0_atan' if label=='resident' else 'audit_atan' if label=='Qfplib' else label+'_atan'
  got,_,n=m.call(name,raw,count=True);outputs[label]=f'{got:016X}';counts[label]=n
  if label!='Qfplib':assert equal(got,expected,64),(label,hex(raw),hex(got),hex(expected))
  assert bytes(m.uc.mem_read(0xd0000060,28))==state,(label,hex(raw),'SIO')
 assert outputs['candidate']==outputs['resident']==outputs['parent']
 # Parent/control fixture byte identity is asserted by build.py.
 rows.append(dict(x=f'{raw:016X}',expected=f'{expected:016X}',outputs=outputs,instructions=counts))
(W/'probe.json').write_text(json.dumps({'status':'PRIVATE_ATAN_COMPONENT_PROBE','rows':rows},indent=2)+'\n')
print(json.dumps([{'x':r['x'],'instructions':r['instructions']} for r in rows],indent=2))
