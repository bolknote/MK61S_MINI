"""Actual sqrt cold-path delta versus exact integer, MPFR and Qfplib."""
from pathlib import Path
from collections import Counter
import hashlib,json,random,struct,sys,time
sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent;ROOT=W.parents[1]
P=ROOT/'.build/m0-asin-scaled-bound-v164-20261023'
Q=ROOT/'.build/m0-float-fma-qualification-20261023'
sys.path.insert(0,str(Q));sys.path.insert(0,str(Q/'support'))
from native_eabi_m0_arm_self_test import Machine,SP
from m0_mpfr_oracle import Oracle
from oracles import integer_sqrt,equal
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
ELF=P/'firmware/mk61s-picocalc-pico-h.elf';REF=ROOT/'.build/m0-v138-execution-20261023/reference/reference.elf'
ROM=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin'
assert sha(ELF)=='3b92d7dc30cc860c0b1f17943f1cd626f94112a98adaf165ec4f9cd300364db1'
assert sha(REF)=='b66da3a6805ecd110580e6dd281e17c37bc4399bee0ba1fae86f8c8cf78bfc26'
assert sha(ROM)=='ef07d54bdd259c7858483606118a3c704976801823c38ac5a2fcdffacd2d83fe'
candidate=Machine(W/'candidate.elf',True,stack_bytes=32)
parent=Machine(ELF,True,stack_bytes=4096,bootrom=ROM)
reference=Machine(REF,True,stack_bytes=4096)
SIGN=1<<63;H=1<<52;jobs={}
def add(raw,tag):jobs.setdefault(raw,tag)
for v in (0,1,2,3,H-1,H,H+1,0x3ff0000000000000,0x4000000000000000,0x7fefffffffffffff,0x7ff0000000000000,0x7ff0000000000001,0x7ff8000000000000,0x7fffffffffffffff):
 for s in (0,SIGN):add(v|s,'special_edges')
if '--all' in sys.argv:
 for E in range(2048):
  for f in (0,1,H-1):
   for s in (0,SIGN):add((E<<52)|f|s,'all_exponent_fields')
 for bit in range(52):
  for delta in (-2,-1,0,1,2):
   v=(1<<bit)+delta
   if 0<v<H:
    for s in (0,SIGN):add(v|s,'subnormal_coefficient_boundaries')
 for bit in range(52):
  for payload in (1<<bit,(1<<bit)-1,((1<<bit)+1)&(H-1)):
   if payload:
    for s in (0,SIGN):add(0x7ff0000000000000|payload|s,'NaN_sign_payload_bits')
 rng=random.Random(0x5A7C01D)
 for _ in range(2048):add(rng.getrandbits(64),'random_raw_fields')
states=(bytes(28),struct.pack('<7I',17,3,17,3,5,2,3));o=Oracle();rows=[];start=time.monotonic()
for index,(raw,tag) in enumerate(jobs.items()):
 expected=integer_sqrt(raw,64);assert equal(expected,o.reference('sqrt',raw),64)
 outputs={};counts={};correct={}
 for label,machine,name in [('candidate',candidate,'mk61_m0_sqrt'),('parent',parent,'mk61_m0_sqrt'),('Qfplib',reference,'qfp_dsqrt')]:
  state=states[index%2];machine.uc.mem_write(0xd0000060,state)
  got,_,n=machine.call(name,raw,count=True)
  assert bytes(machine.uc.mem_read(0xd0000060,28))==state
  outputs[label]=f'{got:016X}';counts[label]=n;correct[label]=equal(got,expected,64)
  if label!='Qfplib':assert correct[label],(label,hex(raw),hex(got),hex(expected))
 assert outputs['candidate']==outputs['parent'],('NaN sign/payload policy',hex(raw),outputs)
 assert counts['candidate']<=counts['parent'],('instruction regression',hex(raw),counts)
 rows.append(dict(x=f'{raw:016X}',group=tag,expected=f'{expected:016X}',outputs=outputs,instructions=counts,correct=correct))
 if len(rows)%4096==0:print('progress',len(rows),'/',len(jobs),flush=True)
def kind(raw):
 E=(raw>>52)&2047;mag=raw&(SIGN-1)
 if not mag:return 'signed_zero'
 if raw==0x7ff0000000000000:return 'positive_infinity'
 if E==2047:return 'other_nonfinite'
 if raw&SIGN:return 'negative_finite'
 return 'positive_subnormal' if E==0 else 'positive_normal'
groups=[]
for category in ('signed_zero','positive_infinity','other_nonfinite','negative_finite','positive_subnormal','positive_normal'):
 rs=[r for r in rows if kind(int(r['x'],16))==category];both=[r for r in rs if r['correct']['Qfplib']]
 groups.append(dict(group=category,cases=len(rs),vs_parent=dict(Counter('faster' if r['instructions']['candidate']<r['instructions']['parent'] else 'equal' for r in rs)),
                    instruction_savings=dict(Counter(r['instructions']['parent']-r['instructions']['candidate'] for r in rs)),Qfplib_wrong=sum(not r['correct']['Qfplib'] for r in rs),
                    parent_slower_correct_Qfplib=sum(r['instructions']['parent']>r['instructions']['Qfplib'] for r in both),candidate_slower_correct_Qfplib=sum(r['instructions']['candidate']>r['instructions']['Qfplib'] for r in both)))
inf=next(r for r in rows if r['x']=='7FF0000000000000');assert inf['instructions']=={'candidate':12,'parent':15,'Qfplib':12}
report=dict(status='PASS_SQRT_COLD_INTEGER_MPFR_ARM_NOT_PRODUCTION',cases=len(rows),ARM_calls=3*len(rows),groups=groups,positive_infinity=inf,
            rows=rows,source_files={n:sha(W/n) for n in ('native_eabi_m0.S','native_eabi_m0_sqrt_special.S.inc')},candidate_ELF_sha256=sha(W/'candidate.elf'),input_ELF_sha256=sha(ELF),reference_ELF_sha256=sha(REF),
            candidate_stack_bytes_written=SP-candidate.stack_lowest,candidate_mapped_firmware_or_ROM=False,MPFR_version=o.version,
            NaN_sign_payload_parent_exact_every_call=True,PCS_SP_bounded_writes_checked_every_call=True,READY_DIRTY_SIO_preserved_every_call=True,instructions_are_not_cycles=True,
            elapsed_seconds=time.monotonic()-start,canonical_or_frozen_changed=False,hardware_accessed=False,goal_complete=False)
name='qualification.json' if '--all' in sys.argv else 'smoke.json'
(W/name).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
