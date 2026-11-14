#!/usr/bin/env python3
"""Actual NRZ4 sender/configuration ARM code, modeled DMA/PIO, no device I/O."""
from pathlib import Path
import argparse,hashlib,json,struct
import host_test as shared
from host_test import Machine,ELF,pack,words,pattern,PB,PC,I2C,DMA,CH7,TIM,RCC,OUTPUT,CALLBACK
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_READ
from unicorn.arm_const import *
CH5=DMA+0x58
class NrzMachine(Machine):
 def __init__(self,package,fault=None):
  super().__init__(package,5,fault);self.nibbles=[]
  self.initial.update({CH5:1 if fault=='dma5_owned' else 0,CH5+4:0,CH5+8:0,CH5+12:0,TIM+60:0})
  if fault=='dma5_irq_owned':self.initial[0xe000e100]|=1<<15
  if fault=='pmu_dma_owned':self.initial[0x40005804]=1<<11
  for at,value in self.initial.items():self.w(at,value)
 def write(self,u,access,at,size,value,user):
  if at==TIM+60:
   if value==self.r(TIM+36):self.w(TIM+16,self.r(TIM+16)|8)
   self.writes.append((at,value));return
  if at in(CH5,CH5+4,CH5+8,CH5+12):self.writes.append((at,value));return
  super().write(u,access,at,size,value,user)
 def code(self,u,pc,size,user):
  active=self.active_dma;self.active_dma=False
  original=self.fault
  if original=='dma5_stall':self.fault='dma_stall'
  super().code(u,pc,size,user);self.fault=original;self.active_dma=active
  if not active or self.instructions%16 or original=='dma_stall':return
  if original in('dma_error','dma5_error')and self.dma_writes==8:
   self.w(DMA,self.r(DMA)|(1<<(19 if original=='dma5_error' else 27)));self.active_dma=False;return
  moved=[]
  for channel,port,shift in((CH7,PB,24),(CH5,PC,16)):
   if channel==CH5 and original=='dma5_stall':continue
   n=self.r(channel+4)
   if not n:continue
   at=self.r(channel+12);self.bsrr(port,self.r(at));self.w(channel+12,at+4);self.w(channel+4,n-1)
   moved.append(channel)
   if n==1:self.w(DMA,self.r(DMA)|(3<<shift))
  if len(moved)==2:
   b=self.r(PB+12);c=self.r(PC+12)
   self.nibbles.append(((b>>9)&1)|((b>>7)&2)|((c>>9)&4)|((c>>7)&8));self.dma_writes+=1
  if not self.r(CH5+4)and not self.r(CH7+4):self.active_dma=False
 def decoded(self,n):
  assert len(self.nibbles)==n//4*10+1
  data=bytearray()
  for frame in range(n//4):
   block=self.nibbles[frame*10:frame*10+10];assert block[0]==0 and block[9]==15
   data.extend((block[i]<<4)|block[i+1]for i in(1,3,5,7))
  assert self.nibbles[-1]==15
  return bytes(data)

def pio_configuration(kit,n,rate):
 """Execute actual Pico configure() plus sealed resident PIO SDK code."""
 manifest=json.loads((kit/'manifest.json').read_text());pe=ELF(kit/'app/FASTLINK.elf')
 native=ELF(Path(manifest['resident_elf_path']));u=shared.Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
 for at,size in((0x10000000,0x1c0000),(0x20000000,0x42000),(0x40000000,0x60000),
                (0x50000000,4096),(0x50200000,0x4000),(0xd0000000,4096)):u.mem_map(at,size)
 for seg in native.segments:
  if seg['data']:u.mem_write(seg['address'],seg['data'])
 delta=0x20000
 for seg in pe.segments:
  if seg['data']:u.mem_write(seg['address']+delta,seg['data'])
 def read(at):return struct.unpack('<I',u.mem_read(at,4))[0]
 def write(at,v):u.mem_write(at,pack(v))
 for at,kind in pe.relocations():
  if kind==2:
   value=read(at+delta)
   if 0x20000000<=value<0x20000000+manifest['app']['memory_bytes']:write(at+delta,value+delta)
  else:assert kind in(3,10,30,42),kind
 def symbol(name):return pe.symbols[name]['value']+delta
 write(symbol('sm'),0);write(symbol('channel'),0);write(symbol('program_at'),0xffffffff)
 write(0x50200004,0x0f000f00)
 def peripheral_read(uc,access,at,size,value,user):
  if 0xd0000100<=at<0xd0000180:write(at,1)
 u.hook_add(UC_HOOK_MEM_READ,peripheral_read)
 for register,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),(5,n,rate)):u.reg_write(register,value)
 u.reg_write(UC_ARM_REG_SP,0x2003f000);u.reg_write(UC_ARM_REG_LR,0x2003e001);u.reg_write(UC_ARM_REG_XPSR,0x1000000)
 u.emu_start(symbol('configure')|1,0x2003e000,count=200000)
 assert u.reg_read(UC_ARM_REG_PC)==0x2003e000,hex(u.reg_read(UC_ARM_REG_PC))
 assert u.reg_read(UC_ARM_REG_R0)==0
 offset=read(symbol('program_at'));program=[read(0x50200048+4*(offset+i))&65535 for i in range(8)]
 sm=0x502000c8
 assert read(sm)=={72:4000,48:2667,36:2000}[rate]<<8
 assert read(0x50000008)==n//2 and read(0x50000004)==symbol('received')
 assert read(0x50200010)==n//4-1 and read(sm+16)==0x6040
 assert read(sm+8)&(1<<31)and read(sm+8)&(1<<16)
 return program,offset

def pio_decode(program,offset,nibbles,n,phase=0.0,pc_skew=0.0,symbol_ticks=8.0):
 """Independent PIO instruction/timing model; FIFO drained by ideal DMA."""
 pc=offset;x=0;y=n//4-1;tick=0;isr=count=0;fifo=[];start=2.0+phase
 def value(t):
  def lane(delay):
   index=int((t-start-delay)//symbol_ticks)
   return 15 if index<0 or index>=len(nibbles)else nibbles[index]
  return(lane(0)&3)|(lane(pc_skew)&12)
 for _ in range(100000):
  word=program[pc-offset];op=word>>13;delay=(word>>8)&31;next_pc=pc+1
  if op==1:
   assert word&0x60==0 and word&31==6
   if bool(value(tick)&1)!=bool(word&128):tick+=1;continue
  elif op==7:
   assert(word>>5)&7==1;x=word&31
  elif op==2:
   assert word&31==4;isr=((isr<<4)|value(tick))&0xffffffff;count+=4
   if count==32:fifo.append(isr);isr=count=0
  elif op==4:
   assert word&128==0;fifo.append(isr);isr=count=0
  elif op==0:
   condition=(word>>5)&7;target=word&31
   if condition==2:
    branch=x!=0;x=(x-1)&0xffffffff
   elif condition==4:
    branch=y!=0;y=(y-1)&0xffffffff
   else:
    assert condition==0;branch=True
    if pc==target:break
   if branch:next_pc=target
  else:raise AssertionError(hex(word))
  tick+=1+delay;pc=next_pc
 else:raise AssertionError('PIO did not reach finite idle')
 if len(fifo)!=n//2:return None
 if any(fifo[2*i+1]!=15 for i in range(n//4)):return None
 return b''.join(fifo[2*i].to_bytes(4,'big')for i in range(n//4))

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--kit',type=Path,default=shared.ROOT/'.build/picocalc-fastlink-20261111/kit-016');args=ap.parse_args();kit=args.kit.resolve()
 package=(kit/'module.s3m').read_bytes();manifest=json.loads((kit/'manifest.json').read_text())
 assert manifest['nrz4']and manifest['modules']['module']['memory_bytes']<=6144
 common=json.loads((kit/'host-shared-test.json').read_text())
 app_sha=hashlib.sha256((kit/'app/FASTLINK.APP').read_bytes()).hexdigest()
 assert common['status']=='PASS'and common['pico_app_sha256']==app_sha and common['sender_reference_only']
 configs={(n,rate):pio_configuration(kit,n,rate)for n in(4,24,48,72,96)for rate in(72,48,36)}
 transfers=pio_cases=0
 for n in(4,24,48,72,96):
  for rate in(72,48,36):
   for kind in range(7):
    machine=NrzMachine(package);assert machine.start(5,n,rate,kind)==0
    machine.now+=500;assert machine.call(1)==0;result=words(machine.u.mem_read(OUTPUT,128))
    assert result[4]==0,result;machine.restored();expected=pattern(n,kind,0x9e3779b9)
    assert machine.decoded(n)==expected;machine.now+=4000;assert machine.call(1)==1;transfers+=1
    program,offset=configs[n,rate]
    for phase in(0.0,0.75,3.5):
     for skew in(0.0,2.0):
      for drift in(0.99,1.0,1.01):
       assert pio_decode(program,offset,machine.nibbles,n,phase,skew,8*drift)==expected,(n,rate,kind,phase,skew,drift)
       pio_cases+=1
 # Consecutive jobs on one resident module catch restore-created timer flags.
 machine=NrzMachine(package)
 for kind in range(7):
  assert machine.start(5,24,72,kind)==0;machine.now+=500;assert machine.call(1)==0
  assert words(machine.u.mem_read(OUTPUT,128))[4]==0;machine.restored()
  machine.now+=4000;assert machine.call(1)==1
 machine=NrzMachine(package);machine.w(TIM+16,8)
 assert machine.start(5,24,72,6)==0;machine.now+=500;assert machine.call(1)==0
 assert words(machine.u.mem_read(OUTPUT,128))[23]==0x08010001;machine.restored()
 machine.now+=4000;assert machine.call(1)==1;machine.w(TIM+16,8);machine.initial[TIM+16]=8
 assert machine.start(5,24,72,6)==0;machine.now+=500;assert machine.call(1)==0
 assert words(machine.u.mem_read(OUTPUT,128))[4]==13;machine.restored()
 faults={}
 for fault in('busy','clock','uart','pending_i2c','timer_owned','dma_owned','dma5_owned','dma5_irq_owned','pmu_dma_owned','dma_error','dma5_error','dma_stall','dma5_stall','restore_line'):
  machine=NrzMachine(package,fault);assert machine.start(5,24,72,6)==0
  machine.now+=500;assert machine.call(1)==0;result=words(machine.u.mem_read(OUTPUT,128))
  assert result[4]>0,(fault,result);machine.restored();assert machine.call(2)==1;machine.restored();faults[fault]=result[4]
 for size in(0,1,3,97):
  machine=NrzMachine(package);assert machine.start(5,size,72,6)==2 and not machine.writes
 for rate in(0,8,73):
  machine=NrzMachine(package);assert machine.start(5,24,rate,6)==2 and not machine.writes
 machine=NrzMachine(package);assert machine.start(5,48,72,6)==0;machine.now+=500;assert machine.call(1)==0
 program,offset=configs[48,72];expected=pattern(48,6,0x9e3779b9)
 assert pio_decode(program,offset,machine.nibbles,48,symbol_ticks=9.6)!=expected
 result={'status':'PASS','physical_io':False,'hardware_timing_measured':False,'module_sha256':hashlib.sha256(package).hexdigest(),
  'pico_app_sha256':app_sha,'actual_ARM_NRZ4_cases':transfers,'PIO_instruction_model_cases':pio_cases,
  'actual_Pico_configuration_cases':len(configs),'faults':faults,'invalid_inputs':7,
  'consecutive_timer_restore_jobs':7,
  'owned_startup_CC3IF_cleanup_once_then_reject':True,
  'module_memory_bytes':manifest['modules']['module']['memory_bytes'],'shared_guards':common,
  'scope':'Actual relocated sender/configuration and exact resident SDK; modeled GPIO/DMA/PIO timing, not electrical validation'}
 (kit/'host-test.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
