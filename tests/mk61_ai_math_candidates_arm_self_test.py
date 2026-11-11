#!/usr/bin/env python3
"""Execute private matrix probes on ARM/ROM; no USB access or firmware write."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from prepare_mk61_ai_math_candidates import records,VARIANTS
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package-dir',type=Path,required=True)
 p.add_argument('--rom',type=Path,default=ROOT/'research/rp2040-memset-2026-10-21/capture/bootrom.bin');a=p.parse_args();base=a.package_dir.resolve()
 meta=json.loads((base/'package.json').read_text())
 for name,h in meta['source_pins'].items():assert sha(ROOT/name)==h,name
 for name,h in meta['generated'].items():assert sha(base/name)==h,name
 assert sha(meta['resident_elf'])==meta['resident_elf_sha256']
 from native_eabi_m0_arm_self_test import Machine,SP
 from unicorn import UC_HOOK_CODE
 from unicorn.arm_const import UC_ARM_REG_PC,UC_ARM_REG_LR
 from check_stm32_vectors import ElfImage
 from tools.apps.packer.app_relocations import extract
 class Probe(Machine):
  def __init__(self):
   self.allowed=[];super().__init__(meta['resident_elf'],True,stack_bytes=16384,instruction_budget=10000000,bootrom=a.rom)
  def write(self,uc,access,address,size,value,user):
   if any(lo<=address and address+size<=hi for lo,hi in self.allowed):return
   return super().write(uc,access,address,size,value,user)
 m=Probe();app=ElfImage(base/'app/MATHCAND.elf');manifest=json.loads((base/'app/MATHCAND.json').read_text());delta=0x20020000-0x20000000
 image=bytearray(app.bytes_at(app.named_sections['.module_image']))
 offsets,_=extract(base/'app/MATHCAND.elf',0x20000000,manifest['image_bytes'],manifest['memory_bytes'])
 for offset in offsets:
  old=struct.unpack_from('<I',image,offset)[0];struct.pack_into('<I',image,offset,old+delta)
 m.uc.mem_write(0x20020000,bytes(image));bss=app.named_sections['.module_bss']
 m.allowed.append((bss[3]+delta,bss[3]+delta+bss[5]))
 # The packer combines initialized data with the SRAM image. These two
 # mutable objects have nonzero default members and therefore are not BSS.
 for name in ('_ZN12_GLOBAL__N_18originalE','_ZN12_GLOBAL__N_14jobsE'):
  address=app.symbols[name]+delta;m.allowed.append((address,address+app.sizes[name]))
 # Bind the unchanged resident runtime just as native APP startup does.
 if 'mk61_app_runtime' in app.symbols:
  runtime=next(v for name,v in m.elf.symbols.items() if name.endswith('native_runtimeE'))
  m.uc.mem_write(app.symbols['mk61_app_runtime']+delta,struct.pack('<I',runtime))
 tables=0x2002d000;table_bytes=14*2050
 assert 0x20020000+manifest['memory_bytes']<tables-16
 m.allowed.append((tables,tables+table_bytes))
 for name,address in app.symbols.items():
  if name.startswith('m0_math_'):m.elf.symbols[name]=address+delta
 pointer=next(address for name,address in m.elf.symbols.items() if '6mk61ai4math' in name and name.endswith('5tableE'))
 m.allowed.append((pointer,pointer+4));m.call('_ZN6mk61ai4math10initializeEv',0,width=32)
 # Simulate an accepted core1 job by executing its actual callback inline.
 # The numerical code, APP adapters, guard, and arguments are all real ARM;
 # only the resident asynchronous mailbox scheduling is substituted.
 shim=0x081fd000
 m.uc.mem_write(shim,bytes.fromhex('10b50c46a047012010bd'))
 symbols=m.elf.symbols
 submit=next(v for n,v in symbols.items() if n.startswith('_ZN8picocalc9io_worker14submit_compute'))&~1
 join=next(v for n,v in symbols.items() if n.startswith('_ZN8picocalc9io_worker12join_compute'))&~1
 mailbox=dict(pending=False,submits=0,joins=0,refuse=False)
 def submit_hook(uc,address,size,user):
  del address,size,user
  assert not mailbox['pending'],'Overlapping unjoined compute submission'
  mailbox['submits']+=1
  if mailbox['refuse']:
   from unicorn.arm_const import UC_ARM_REG_R0
   uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  else:
   mailbox['pending']=True;uc.reg_write(UC_ARM_REG_PC,shim|1)
 def join_hook(uc,address,size,user):
  del address,size,user
  assert mailbox['pending'],'Blocking native join called on IDLE'
  mailbox['pending']=False;mailbox['joins']+=1
  uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
 m.uc.hook_add(UC_HOOK_CODE,submit_hook,begin=submit,end=submit)
 m.uc.hook_add(UC_HOOK_CODE,join_hook,begin=join,end=join)
 m.uc.mem_write(m.elf.symbols['m0_math_tables'],struct.pack('<I',tables))
 header=m.elf.symbols['m0_math_header'];payload=m.elf.symbols['m0_math_payload'];result=m.elf.symbols['m0_math_result'];checks=0;rows=[]
 for offset,h,data in records((base/'MATHCASE.BIN').read_bytes()):
  del offset
  assert zlib.crc32(data)==h[15]
  m.uc.mem_write(header,struct.pack('<16I',*h));m.uc.mem_write(payload,data)
  assert m.call('m0_math_load',0,width=32)[0]&0xffffffff==1
  rows_in_case=h[3];expected=list(struct.unpack_from('<'+'I'*rows_in_case,data,len(data)-rows_in_case*4))
  best_id,best_bits=h[9],h[10]
  score=lambda v:struct.unpack('<f',struct.pack('<I',v))[0]
  for i,bits in enumerate(expected):
   if score(bits)>score(best_bits) or (score(bits)==score(best_bits) and h[6]+i<best_id):best_id,best_bits=h[6]+i,bits
  for v,name in enumerate(VARIANTS):
   if v>=4 and not h[8]:continue
   for all_logits in ((0,1) if v>=4 else (0,)):
    for cores,entry in ((1,'m0_math_probe'),(2,'m0_math_pair_probe')):
     calls=(mailbox['submits'],mailbox['joins'])
     assert m.call(entry,v,all_logits,width=32)[0]&0xffffffff==1,(h[0],name,cores,all_logits)
     assert not mailbox['pending']
     assert (mailbox['submits'],mailbox['joins'])==tuple(n+int(cores==2) for n in calls)
     r=struct.unpack('<35I',m.uc.mem_read(result,140))
     assert r[0]==1 and (r[5],r[6])==(best_id,best_bits),(h[0],name,cores,r[:7])
     if v<4 or all_logits:assert list(r[7:7+rows_in_case])==expected,(h[0],name,cores,'logits')
     if all_logits:assert r[1]==0
     rows.append(dict(case=h[0],variant=name,cores=cores,all_logits=bool(all_logits),groups=r[2],bounds=r[3],pruned=r[1]))
     checks+=1
  mailbox['refuse']=True;joins=mailbox['joins']
  assert m.call('m0_math_pair_probe',0,0,width=32)[0]&0xffffffff==0
  assert not mailbox['pending'] and mailbox['joins']==joins
  mailbox['refuse']=False
  # Broken CRC and a malicious underestimated norm cannot become a bound.
  changed=bytearray(data);changed[0]^=1;m.uc.mem_write(payload,bytes(changed))
  assert m.call('m0_math_load',0,width=32)[0]&0xffffffff==0
  changed=bytearray(data);norm_at=h[4]+h[5]*8+h[11]*2+h[12]
  norm=struct.unpack_from('<H',changed,norm_at)[0];struct.pack_into('<H',changed,norm_at,norm^1)
  bad=list(h);bad[15]=zlib.crc32(changed);m.uc.mem_write(header,struct.pack('<16I',*bad));m.uc.mem_write(payload,bytes(changed))
  assert m.call('m0_math_load',0,width=32)[0]&0xffffffff==0
 stack_used=SP-m.stack_lowest
 # A whole probe includes preparation, dispatch, collection and the kernel;
 # core1 runs only calculate(). Reserve at least half its2KiB stack for the
 # worker/interrupt frames, beyond the emulated numerical call chain.
 assert stack_used<1024,('Numerical probe exceeds conservative core1 budget',stack_used)
 out=dict(status='ARM_ROM_PASS',physical_io=False,cases=len(meta['cases']),checks=checks,
          actual_resident_baseline=True,all_logits_fallback_bit_exact=True,
          CRC_corruption_rejected=True,underestimated_norm_rejected=True,
          bound_includes_FP32_rounding=True,callee_saved_SP_and_write_ranges_checked=True,
          maximum_numerical_probe_stack_bytes=stack_used,core1_stack_bytes=2048,
          stack_measurement_scope='Probe call chain only; excludes native service/worker/IRQ frames',
          two_core_dispatch_executed=True,worker_refusal_fails_without_join=True,
          asynchronous_mailbox_scheduling='Inline actual ARM callback via submit shim; not physical concurrency',
          app_sha256=sha(base/'app/MATHCAND.APP'),ROM_sha256=sha(a.rom),
          physical_timing=None,checks_detail=rows)
 (base/'arm-results.json').write_text(json.dumps(out,indent=2)+'\n')
 print('ARM/ROM:',len(meta['cases']),'real matrix tiles;',checks,'exact probes; CRC/norm faults rejected; full-logit fallback PASS')
if __name__=='__main__':main()
