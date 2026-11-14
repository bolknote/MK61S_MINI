#!/usr/bin/env python3
"""Actual relocated ARM module execution, GPIO/DMA model, independent decoder.

The time and DMA models exercise control flow and restoration. They are not
physical timing, electrical validation or an estimate of ARM cycle counts.
"""
from pathlib import Path
import argparse,hashlib,json,struct,sys,zlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'sdk/coproc')]
from unicorn_runtime import Uc
from unicorn import UC_ARCH_ARM,UC_MODE_MCLASS,UC_MODE_THUMB,UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn.arm_const import *
from elf32 import ELF
PB=0x40010c00;PC=0x40011000;I2C=0x40005400;UART=0x40004800
DMA=0x40020000;CH7=DMA+0x80;TIM=0x40000800;RCC=0x40021000
API=0x20004000;JOB=API+32;INPUT=API+128;OUTPUT=API+256
CALLBACK=0x08001000;STOP=CALLBACK+16;BASE=0x20000800;STACK=0x20004f00
def pack(v):return struct.pack('<I',v&0xffffffff)
def words(data):return struct.unpack('<'+'I'*(len(data)//4),data)
def pattern(n,kind,seed):
 out=bytearray()
 for i in range(n):
  seed^=(seed<<13)&0xffffffff;seed^=seed>>17;seed^=(seed<<5)&0xffffffff
  out.append((0,255,0x55,0xaa,1<<(i%8),255^(1<<(i%8)),seed&255)[kind])
 return bytes(out)

class Machine:
 def __init__(self,package,mode=1,fault=None):
  self.u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
  for at,n in ((0x08000000,65536),(0x20000000,20480),(0x40000000,0x30000),(0xe0000000,0x100000)):
   self.u.mem_map(at,n)
  header=words(package[:64]);image=bytearray(package[64:64+header[4]])
  for at in words(package[64+header[4]:]):
   struct.pack_into('<I',image,at,struct.unpack_from('<I',image,at)[0]+BASE-0x20000000)
  self.u.mem_write(BASE,bytes(image));self.entry=BASE+header[6]
  self.w(API,1);self.w(API+4,16);self.w(API+8,CALLBACK|1)
  self.w(JOB,INPUT);self.w(JOB+8,OUTPUT);self.w(JOB+12,512)
  self.now=100;self.instructions=0;self.mode=mode;self.fault=fault;self.active_dma=False
  self.gpio=[];self.writes=[];self.dma_writes=0;self.timeout_calls=0;self.filter_stage=0;self.minimum_sp=STACK
  self.initial={RCC+4:0x001d040a,RCC+28:0x00260000,PB+4:0x888888ff,PC+4:0x88888b88,
   PB+12:0xa5a5,PC+12:0x5a5a,I2C:0x401,I2C+4:0x324,I2C+0x14:0,I2C+0x18:0,
   I2C+8:0x403e,I2C+12:0,I2C+28:180,I2C+32:37,
   UART:0xc0,UART+12:0x200c,UART+20:0xc0,DMA+0x30:0x20af,DMA+0x34:400,
   DMA+0x1c:0,DMA+0x20:0,CH7:0,CH7+4:0,CH7+8:0,CH7+12:0,
   TIM:0,TIM+12:0,TIM+16:0,TIM+24:0,TIM+28:0,TIM+32:0,
   TIM+36:0,TIM+40:0,TIM+44:65535,0xe0001000:0,0xe0001004:17,0xe000edfc:0,
   0x40010004:0x32008000,0xe000e100:0,0xe000e104:1,0xe000e200:0,0xe000e204:0}
  if fault=='busy':self.initial[I2C+0x18]=2
  if fault=='timer_owned':self.initial[RCC+28]|=4
  if fault=='dma_owned':self.initial[CH7]=1
  if fault=='clock':self.initial[RCC+4]=0
  if fault=='uart':self.initial[UART]=0xc8
  if fault=='pending_i2c':self.initial[0xe000e200]=0x80000000
  for at,v in self.initial.items():self.w(at,v)
  self.u.hook_add(UC_HOOK_CODE,self.code)
  self.u.hook_add(UC_HOOK_MEM_READ,self.read)
  self.u.hook_add(UC_HOOK_MEM_WRITE,self.write)
 def r(self,at):return struct.unpack('<I',self.u.mem_read(at,4))[0]
 def w(self,at,v):self.u.mem_write(at,pack(v))
 def code(self,u,pc,size,unused):
  self.instructions+=1
  self.minimum_sp=min(self.minimum_sp,u.reg_read(UC_ARM_REG_SP))
  if self.active_dma and self.instructions%16==0 and self.fault!='dma_stall':
   n=self.r(CH7+4)
   if n:
    if self.fault=='dma_error' and self.dma_writes==8:
     self.w(DMA,self.r(DMA)|(1<<27));self.active_dma=False
    else:
     at=self.r(CH7+12);value=self.r(at);self.bsrr(PB,value);self.w(CH7+12,at+4);self.w(CH7+4,n-1)
     self.dma_writes+=1
     if n==1:self.w(DMA,self.r(DMA)|(3<<24));self.active_dma=False
  if pc==CALLBACK:
   self.now+=1
   if self.fault in ('timeout','dma_stall') and self.r(I2C)&1==0:
    self.timeout_calls+=1
    if self.timeout_calls>3:self.now+=2000
   u.reg_write(UC_ARM_REG_R0,self.now);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
 def read(self,u,access,at,size,value,unused):
  if at==0xe0001004 and self.r(0xe0001000)&1:self.w(at,self.instructions)
  if at==PB+8 and self.fault=='restore_line' and self.r(PB+4)&255==0x77:self.w(at,self.r(at)&~0x200)
 def bsrr(self,port,value):
  mask=0x300 if port==PB else 0xc00
  assert (value&0xffff|value>>16)&~mask==0,hex(value)
  old=self.r(port+12);new=(old&~(value>>16))|(value&0xffff);self.w(port+12,new)
  if port==PB:self.w(PB+8,(self.r(PB+8)&~0x300)|(new&0x300))
  if port==PB and self.r(PB+4)&255==0x77:
   expected=(0x300,0x100,0,0x100,0x300)
   if self.filter_stage<5 and new&0x300==expected[self.filter_stage]:self.filter_stage+=1
  clock=0x200 if self.mode==2 else 0x100
  if port==PB and not(old&clock) and new&clock and self.r(PB+4)&255==0x33:
   if self.mode==2:
    c=self.r(PC+12);self.gpio.append(((new>>8)&1)|((c>>10)&2)|((c>>8)&4))
   else:self.gpio.append((new>>9)&1)
 def write(self,u,access,at,size,value,unused):
  assert not any(at<address+length and address<at+size for address,length in ((0x20000629,1),(0x2000062c,4),(0x20000640,2))),'Native M3 observation field was modified'
  if 0x20000000<=at<0x20005000:return
  allowed={PB+4,PB+16,PC+4,PC+16,I2C,I2C+4,UART+12,UART+20,DMA+0x30,
   DMA+4,CH7,CH7+4,CH7+8,CH7+12,RCC+28,0xe0001000,0xe0001004,0xe000edfc,
   I2C+8,I2C+12,I2C+28,I2C+32,
   TIM,TIM+8,TIM+12,TIM+16,TIM+20,TIM+24,TIM+28,TIM+32,TIM+36,TIM+40,TIM+44}
  assert at in allowed,('unowned MMIO write',hex(at),hex(value))
  self.writes.append((at,value))
  if at==PB+16 or at==PC+16:self.bsrr(at-16,value)
  if at in (PB+4,PC+4):
   mask=255 if at==PB+4 else 0xff00
   assert (self.r(at)^value)&~mask==0,'Unrelated GPIO configuration changed'
   if at==PB+4 and value&255==0x33:
    # Fault model: a GPIO lease latches the I2C filter/BUSY state and BERR.
    # Register reset alone does not unlock the filter; verified transitions
    # are required. This models the documented failure, not analog physics.
    self.w(I2C+24,self.r(I2C+24)|2);self.w(I2C+20,self.r(I2C+20)|0x100)
  if at==RCC+28:assert (self.r(at)^value)&~4==0,'Unrelated clock changed'
  if at==DMA+4:self.w(DMA,self.r(DMA)&~value)
  if at==I2C and value&(1<<15):
   for off in (4,8,12,20,24,28,32):self.w(I2C+off,0)
   if self.filter_stage!=5:self.w(I2C+24,2)
  if at==TIM and value&1:self.active_dma=True
  if at==TIM and not value&1:self.active_dma=False
 def call(self,op):
  self.u.reg_write(UC_ARM_REG_R0,op);self.u.reg_write(UC_ARM_REG_R1,API);self.u.reg_write(UC_ARM_REG_R2,JOB)
  self.u.reg_write(UC_ARM_REG_SP,STACK);self.u.reg_write(UC_ARM_REG_LR,STOP|1)
  self.u.reg_write(UC_ARM_REG_XPSR,0x01000000);self.u.reg_write(UC_ARM_REG_PRIMASK,0)
  self.u.emu_start(self.entry|1,STOP,count=3000000)
  assert self.u.reg_read(UC_ARM_REG_PC)==STOP,hex(self.u.reg_read(UC_ARM_REG_PC))
  assert self.u.reg_read(UC_ARM_REG_SP)==STACK and not self.u.reg_read(UC_ARM_REG_PRIMASK)
  assert STACK-self.minimum_sp<=512,'Module exceeds its declared stack hint (without ISRs)'
  return self.u.reg_read(UC_ARM_REG_R0)
 def restored(self):
  # CYCCNT is restored when it was initially disabled; timer/DMA status flags
  # generated by this experiment are acknowledged, never left pending.
  for at,expected in self.initial.items():
   if at in (UART,DMA+0x34):continue
   assert self.r(at)==expected,(hex(at),hex(self.r(at)),hex(expected),self.fault)
  assert self.r(DMA)&0x0f000000==0
 def start(self,mode,n,rate,kind,seed=0x9e3779b9):
  self.u.mem_write(INPUT,struct.pack('<6I',0x314b4c46,mode,n,rate,kind,seed));self.w(JOB+4,24)
  return self.call(0)
 def decode(self,n):
  # PIO executes WAIT low, WAIT high, IN, JMP X--, then a finite idle.
  bits=3 if self.mode==2 else 1
  assert len(self.gpio)==n*8//bits,len(self.gpio)
  fifo=[];isr=count=0
  for symbol in self.gpio:
   isr=((isr<<bits)|symbol)&0xffffffff;count+=bits
   if count==24:fifo.append(isr);isr=count=0
  assert count==0 and len(fifo)==n//3
  return b''.join(v.to_bytes(3,'big') for v in fifo)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--kit',type=Path,default=ROOT/'.build/picocalc-fastlink-20261111/kit-016')
 ap.add_argument('--sender-kit',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
 package=((a.sender_kit or a.kit)/'module.s3m').read_bytes();passed=[]
 for mode in (1,2,3):
  for n in ((3,24) if mode==3 else (3,24,96)):
   for rate in ((36,18,8,4) if mode==3 else (0,)):
    for kind in range(7):
     m=Machine(package,mode);assert m.start(mode,n,rate,kind)==0
     m.now+=500;assert m.call(1)==0;m.now+=4000;assert m.call(1)==1
     result=words(m.u.mem_read(OUTPUT,96));assert result[4]==0,result
     assert result[20]==0 and result[21]==0 and result[22]&2==0,result
     assert m.decode(n)==pattern(n,kind,0x9e3779b9)
     assert result[5]==zlib.crc32(pattern(n,kind,0x9e3779b9));m.restored()
     assert m.call(3)==1;m.restored();passed.append((mode,n,rate,kind))
 for mode in (1,2):
  m=Machine(package,mode);assert m.start(mode,24,8,6)==0;m.now+=500;assert m.call(1)==0
  assert m.decode(24)==pattern(24,6,0x9e3779b9);m.restored();passed.append((mode,24,8,6))
 m3_observation_cases=0
 for state,app,recovery,error in ((0x28,0,0,0),(0x2a,2,1,4)):
  m=Machine(package,1)
  m.u.mem_write(0x20000629,bytes([state]));m.u.mem_write(0x20000640,bytes([app,recovery]));m.w(0x2000062c,error)
  assert m.start(1,24,0,0)==0;m.now+=500;assert m.call(1)==0
  observed=words(m.u.mem_read(OUTPUT,128))
  assert observed[24:29]==(m.initial[I2C],m.initial[I2C+4],m.initial[I2C],m.initial[I2C+4],m.initial[I2C+8])
  assert observed[30]==state|(app<<8)|(recovery<<16) and observed[31]==error
  assert m.u.mem_read(0x20000629,1)==bytes([state]) and m.u.mem_read(0x20000640,2)==bytes([app,recovery])
  m.restored();m3_observation_cases+=1
 failures={}
 for fault in ('busy','timer_owned','dma_owned','clock','uart','pending_i2c','dma_error','dma_stall','timeout','restore_line'):
  mode=3 if fault.startswith('dma') or fault=='timer_owned' else 2
  m=Machine(package,mode,fault);assert m.start(mode,24,8 if mode==3 else 0,6)==0
  m.now+=500;assert m.call(1)==0;result=words(m.u.mem_read(OUTPUT,64))
  assert result[4]>0,(fault,result);m.restored();assert m.call(2)==1;m.restored();failures[fault]=result[4]
 # Preserve the historical defect: old code restores configuration bits but
 # leaves the modeled F1 BUSY/filter fault pending. New cases above clear it.
 old_package=(a.kit/'legacy_module.s3m').read_bytes()
 assert hashlib.sha256(old_package).hexdigest()=='245d2f7d09004d9977d0b14b99e39f84513bea440bad1a52e1ae5da231e8a84a'
 old=Machine(old_package,1);assert old.start(1,24,0,0)==0;old.now+=500;assert old.call(1)==0
 assert old.r(I2C+24)&2 and words(old.u.mem_read(OUTPUT,64))[4]==0
 for mode in (1,2,3):
  m=Machine(package,mode);assert m.start(mode,24,8 if mode==3 else 0,6)==0
  assert m.call(2)==1 and not m.gpio;m.restored()
 for n in (0,1,4,97,0xffffffff):
  m=Machine(package);assert m.start(1,n,0,6)==2 and not m.writes
 # Read-only identity executes against the actual known BIOS and metadata.
 m=Machine((a.kit/'identity.s3m').read_bytes());body=(ROOT/'firmware/picocalc-m3-boot/bios.bin').read_bytes()
 m.u.mem_write(0x08002000,body);header=(ROOT/'firmware/picocalc-m3-boot/BIOS.M3U').read_bytes()[:32]
 m.u.mem_write(0x0800f400,header+pack(0xc001cafe));m.w(0xe0042000,0);m.w(0xe000ed00,0x411fc231)
 # Factory flash-size lies outside the mapped Flash page.
 m.u.mem_map(0x1ffff000,4096);m.u.mem_write(0x1ffff7e0,struct.pack('<H',64))
 m.u.mem_write(INPUT,pack(0x31444946));m.w(JOB+4,4);assert m.call(0)==0
 while m.call(1)==0:pass
 identity_bytes=bytes(m.u.mem_read(OUTPUT,120));result=words(identity_bytes)
 assert result[9]==zlib.crc32(body)==0x3be158b4 and result[10]==0 and result[28]==0x411fc231
 assert not m.writes,'Identity wrote peripherals'
 # Execute the actual Pico restoration function for both two/four-wire
 # leases and a stuck enable-status path. Unrelated GPIOs are canaries.
 pe=ELF(a.kit/'app/FASTLINK.elf');pico_checks=0;identity_cases=0
 ident=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB);ident.mem_map(0x20000000,0x20000)
 for seg in pe.segments:
  if seg['data']:ident.mem_write(seg['address'],seg['data'])
 def guard(data,length=120):
  ident.mem_write(0x2001d000,data);ident.reg_write(UC_ARM_REG_R0,0x2001d000);ident.reg_write(UC_ARM_REG_R1,length)
  ident.reg_write(UC_ARM_REG_SP,0x2001f000);ident.reg_write(UC_ARM_REG_LR,0x2001e001)
  ident.reg_write(UC_ARM_REG_XPSR,0x1000000)
  ident.emu_start(pe.symbols['fl_identity_valid']['value']|1,0x2001e000,count=10000)
  assert ident.reg_read(UC_ARM_REG_PC)==0x2001e000
  return ident.reg_read(UC_ARM_REG_R0)
 for device in (0,0x410,0x20030410):
  data=bytearray(identity_bytes);struct.pack_into('<I',data,40,device);assert guard(bytes(data))==1;identity_cases+=1
 for offset,value in ((0,0),(4,2),(8,0x414),(12,0x08000000),(16,29840),(20,0),(36,0),
                      (40,0x414),(44,128),(48,0),(56,1),(64,1<<12),(108,0),(112,0),
                      (112,0x410fc241),(116,1)):
  data=bytearray(identity_bytes);struct.pack_into('<I',data,offset,value)
  assert guard(bytes(data))==0,(offset,hex(value));identity_cases+=1
 for length in (0,112,119,121):assert guard(identity_bytes,length)==0;identity_cases+=1
 # Actual Pico guard sees normal raw TXNFULL without mistaking it for an
 # enabled IRQ. Every owned enable/force bit and enabled SM must still fail.
 manifest=json.loads((a.kit/'manifest.json').read_text());regs=manifest['register_header']['values']
 ident.mem_map(0x50200000,4096);pio_cases=0
 def pguard(sm):
  ident.reg_write(UC_ARM_REG_R0,sm);ident.reg_write(UC_ARM_REG_SP,0x2001f000)
  ident.reg_write(UC_ARM_REG_LR,0x2001e001);ident.reg_write(UC_ARM_REG_XPSR,0x1000000)
  ident.emu_start(pe.symbols['fl_pio_resources_free']['value']|1,0x2001e000,count=10000)
  assert ident.reg_read(UC_ARM_REG_PC)==0x2001e000
  return ident.reg_read(UC_ARM_REG_R0)
 for sm in range(4):
  for raw in (0xf0,0xfff):
   ident.mem_write(0x50200128,pack(raw));assert pguard(sm)==1;pio_cases+=1
  for reg in regs.values():
   for bit in (sm,sm+4,sm+8):
    ident.mem_write(0x50200000+reg,pack(1<<bit));assert pguard(sm)==0;pio_cases+=1
   ident.mem_write(0x50200000+reg,pack(1<<((sm+1)%4)));assert pguard(sm)==1;pio_cases+=1
   ident.mem_write(0x50200000+reg,pack(0))
  ident.mem_write(0x50200000,pack(1<<sm));assert pguard(sm)==0;pio_cases+=1
  ident.mem_write(0x50200000,pack(0))
 assert pguard(4)==0;pio_cases+=1
 for at in (0x40048000,0x40054000,0xd0000000):ident.mem_map(at,4096)
 fence_results={};fence_time=[0];fence_case=[''];fence_writes=[]
 def fence_read(uc,access,at,size,value,user):
  if at==0x40054028:
   fence_time[0]+=50;uc.mem_write(at,pack(fence_time[0]))
  if 0x40048000<=at<0x40049000 or at==0xd0000004:
   t=fence_time[0];case=fence_case[0];mask=tx=rx=active=0;pins=0xc0
   if case=='delayed' and t<6000:active=0x21
   if case=='never':mask=0x244
   if case=='transient' and 300<=t<6000:active=0x21
   if case=='line_stuck':pins=0x80
   if case=='tx_stuck':tx=1
   if case=='rx_stuck':rx=1
   if case=='active_stuck':active=0x21
   if case=='draining' and t<4000:rx=2
   if case=='glitch' and (t<5000 or 5300<=t<5400):pins=0x80
   values={0x40048030:mask,0x40048074:tx,0x40048078:rx,0x40048070:active,
    0xd0000004:pins,0x40048034:0,0x4004806c:1,0x4004809c:1}
   uc.mem_write(at,pack(values.get(at,0)))
 def fence_write(uc,access,at,size,value,user):
  if not 0x20000000<=at<0x20020000:fence_writes.append((at,value))
 h1=ident.hook_add(UC_HOOK_MEM_READ,fence_read);h2=ident.hook_add(UC_HOOK_MEM_WRITE,fence_write)
 for case in ('idle','delayed','never','transient','line_stuck','tx_stuck','rx_stuck','active_stuck','draining','glitch'):
  fence_time[0]=0;fence_case[0]=case
  ident.reg_write(UC_ARM_REG_R0,0x2001d000);ident.reg_write(UC_ARM_REG_SP,0x2001f000)
  ident.reg_write(UC_ARM_REG_LR,0x2001e001);ident.reg_write(UC_ARM_REG_XPSR,0x1000000)
  ident.emu_start(pe.symbols['fl_i2c_idle_fence']['value']|1,0x2001e000,count=100000)
  assert ident.reg_read(UC_ARM_REG_PC)==0x2001e000
  output=words(ident.mem_read(0x2001d000,44));fence_good=ident.reg_read(UC_ARM_REG_R0)
  expected=case in ('idle','delayed','transient','draining','glitch')
  assert fence_good==expected,(case,fence_good,output)
  assert output[0]<=20100 and (not fence_good or output[10]>=6)
  if case in ('delayed','transient'):assert output[0]>=6400
  if case=='draining':assert output[0]>=4400
  if case=='glitch':assert output[0]>=5800
  fence_results[case]={'accepted':bool(fence_good),'modeled_wait_us':output[0],'samples':output[1]}
 assert not fence_writes,'Idle fence mutated MMIO'
 ident.hook_del(h1);ident.hook_del(h2)
 # Execute the real take_pins path. Native service is modeled at its callback
 # boundary; the full compiled logical fence + physical fence + acquisition
 # run unchanged. Every MMIO write is forbidden until both native fields are
 # zero and the subsequent 500us physical idle interval has elapsed.
 logical_results={};layout=manifest['native_keyboard']
 kp=layout['address']+layout['pending_offset'];phase=layout['address']+layout['phase_offset']
 health_addresses=manifest['native_health']['addresses']
 native_regions=[(address,1 if name=='KBD_ONLINE' else 4)for name,address in health_addresses.items()]+[(kp,1),(phase,1)]
 for scenario in ('idle','delayed','pending_only','phase_only','never','invalid_pending','invalid_phase','boundary','too_late','late_callback','wrap','physical_busy',
                  'native_before_logical','native_in_logical','native_after_logical','native_after_physical','native_late_physical'):
  lp=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
  for at,n in ((0x20000000,0x20000),(0x40014000,4096),(0x4001c000,4096),(0x40038000,4096),
               (0x40048000,4096),(0x40054000,4096),(0xd0000000,4096)):lp.mem_map(at,n)
  for seg in pe.segments:
   if seg['data']:lp.mem_write(seg['address'],seg['data'])
  def lw(at,v):lp.mem_write(at,pack(v))
  def lr(at):return struct.unpack('<I',lp.mem_read(at,4))[0]
  def state(p,q):lp.mem_write(kp,bytes([p]));lp.mem_write(phase,bytes([q]))
  lw(pe.symbols['mk61_api']['value'],0x2001b000)
  lw(0x2001b000+layout['service_api_offset'],0x2001e101)
  if scenario in ('idle','physical_busy','native_before_logical','native_after_logical','native_after_physical','native_late_physical'):state(0,0)
  elif scenario=='phase_only':state(0,2)
  elif scenario=='invalid_pending':state(2,0)
  elif scenario=='invalid_phase':state(0,9)
  else:state(1,0)
  initial=(lp.mem_read(kp,1)[0],lp.mem_read(phase,1)[0])
  for i in range(4):lw(0x40014004+8*(6+i),3 if i<2 else 2);lw(0x4001c004+4*(6+i),0x58)
  lw(0x4004806c,1);lw(0x40038030,0x301);lw(0xd0000004,0xc0)
  elapsed=[0];origin=0xfffff000 if scenario=='wrap' else 0;complete=[0 if initial==(0,0) else None]
  mmio=[];calls=[0]
  def lread(uc,access,at,size,value,user):
   if at==0x40054028:lw(at,origin+elapsed[0]);elapsed[0]+=100
   if at==0x4004809c:lw(at,lr(0x4004806c)&1)
   if at==0x40048070:lw(at,0x21 if scenario in ('physical_busy','native_late_physical') else 0)
  def lcode(uc,pc,size,user):
   if pc==(pe.symbols['fl_native_edge']['value']&~1):
    edge=uc.reg_read(UC_ARM_REG_R0)
    if (scenario=='native_after_logical' and edge==3)or(scenario in ('native_after_physical','native_late_physical') and edge==4):
     lw(health_addresses['I2C_TIMEOUTS'],1)
   if pc!=0x2001e100:return
   calls[0]+=1;elapsed[0]+=400
   if scenario=='native_in_logical':lw(health_addresses['I2C_TIMEOUTS'],1)
   if scenario=='late_callback':elapsed[0]+=120000
   due=99500 if scenario=='boundary' else 100500 if scenario=='too_late' else 3000 if scenario=='phase_only' else 16000 if scenario=='pending_only' else 19000
   if scenario!='never' and elapsed[0]>=due:
    state(0,0)
    if complete[0] is None:complete[0]=elapsed[0]
   elif scenario in ('delayed','wrap') and elapsed[0]>=16000:state(0,2)
   uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
  def lwrite(uc,access,at,size,value,user):
   assert not any(at<start+length and start<at+size for start,length in native_regions),'Native state was patched'
   if at<0x40000000:return
   assert lp.mem_read(kp,1)==b'\0' and lp.mem_read(phase,1)==b'\0','Acquisition before full logical completion'
   assert complete[0] is not None and elapsed[0]-complete[0]>=500,'Acquisition before stable physical idle'
   mmio.append((at,value))
  lp.hook_add(UC_HOOK_MEM_READ,lread);lp.hook_add(UC_HOOK_MEM_WRITE,lwrite);lp.hook_add(UC_HOOK_CODE,lcode)
  lp.reg_write(UC_ARM_REG_SP,0x2001f000);lp.reg_write(UC_ARM_REG_LR,0x2001e001);lp.reg_write(UC_ARM_REG_XPSR,0x1000000)
  lp.emu_start(pe.symbols['fl_native_start']['value']|1,0x2001e000,count=10000)
  if scenario=='native_before_logical':lw(health_addresses['I2C_TIMEOUTS'],1)
  lp.reg_write(UC_ARM_REG_SP,0x2001f000);lp.reg_write(UC_ARM_REG_LR,0x2001e001);lp.reg_write(UC_ARM_REG_XPSR,0x1000000)
  lp.emu_start(pe.symbols['take_pins']['value']|1,0x2001e000,count=100000)
  assert lp.reg_read(UC_ARM_REG_PC)==0x2001e000
  code=lp.reg_read(UC_ARM_REG_R0);native_fault=scenario.startswith('native_')
  success=scenario not in ('never','invalid_pending','invalid_phase','too_late','late_callback','physical_busy')and not native_fault
  assert code==(0 if success else (-45 if native_fault else -30 if scenario=='physical_busy' else -44)&0xffffffff),(scenario,hex(code))
  assert bool(mmio)==success,(scenario,mmio)
  if scenario in ('idle','invalid_pending','invalid_phase','physical_busy'):assert calls[0]==0
  logical_results[scenario]={'accepted':success,'modeled_us':elapsed[0],'service_calls':calls[0],'MMIO_acquisition_writes':len(mmio)}
 # Every diagnostic boundary independently detects each native counter. Run
 # the actual ARM sampler/latch, preserve nonzero pre-existing counters and
 # forbid all guest writes to resident fields or peripheral registers.
 health_cases=[]
 for boundary in range(1,10):
  for changed in ('I2C_TIMEOUTS','I2C_RESETS','I2C_ABORTS','KBD_ERRORS'):
   nh=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
   nh.mem_map(0x20000000,0x20000);nh.mem_map(0x40054000,4096)
   nh.mem_map(0x40048000,4096);nh.mem_map(0xd0000000,4096)
   for seg in pe.segments:
    if seg['data']:nh.mem_write(seg['address'],seg['data'])
   def hw(at,value):nh.mem_write(at,pack(value))
   def hr(at):return struct.unpack('<I',nh.mem_read(at,4))[0]
   def hs(name):return pe.symbols[name]['value']
   for name,value in [('I2C_TIMEOUTS',7),('I2C_RESETS',7),('I2C_ABORTS',0),('KBD_ERRORS',7),('I2C_STAGE',0),('I2C_RESULT',2)]:hw(health_addresses[name],value)
   nh.mem_write(kp,b'\0');nh.mem_write(phase,b'\0');nh.mem_write(health_addresses['KBD_ONLINE'],b'\1')
   stamp=[0]
   def nread(uc,access,at,size,value,user):
    if at==0x40054028:stamp[0]+=17;hw(at,stamp[0])
   def nwrite(uc,access,at,size,value,user):
    assert at<0x40000000,'Health probe wrote MMIO'
    assert not any(at<start+length and start<at+size for start,length in native_regions),'Health probe wrote native state'
   nh.hook_add(UC_HOOK_MEM_READ,nread);nh.hook_add(UC_HOOK_MEM_WRITE,nwrite)
   def ncall(name,arg=0):
    nh.reg_write(UC_ARM_REG_R0,arg);nh.reg_write(UC_ARM_REG_SP,0x2001f000)
    nh.reg_write(UC_ARM_REG_LR,0x2001e001);nh.reg_write(UC_ARM_REG_XPSR,0x1000000)
    nh.emu_start(hs(name)|1,0x2001e000,count=10000)
    assert nh.reg_read(UC_ARM_REG_PC)==0x2001e000
    return nh.reg_read(UC_ARM_REG_R0)
   ncall('fl_native_start');assert ncall('fl_native_edge',boundary-1)==1
   previous=nh.mem_read(hs('fl_native_previous'),64)
   hw(health_addresses[changed],hr(health_addresses[changed])+1)
   hw(health_addresses['I2C_STAGE'],3);hw(health_addresses['I2C_RESULT'],-2)
   assert ncall('fl_native_edge',boundary)==0 and hr(hs('fl_native_fault'))==boundary
   assert nh.mem_read(hs('fl_native_fault_before'),64)==previous
   assert hr(hs('fl_native_fault_previous_edge'))==boundary-1
   after=nh.mem_read(hs('fl_native_fault_after'),64)
   assert words(after)[5:7]==(3,0xfffffffe)
   hw(health_addresses['I2C_STAGE'],0);assert ncall('fl_native_edge',boundary+10)==0
   assert hr(hs('fl_native_fault'))==boundary and nh.mem_read(hs('fl_native_fault_after'),64)==after
   assert words(nh.mem_read(hs('fl_native_baseline'),64))[1:5]==(7,7,0,7)
   health_cases.append({'boundary':boundary,'counter':changed,'first_fault_latched':True,'native_state_read_only':True})
 # Run the exact resident SDK allocators used by the APP. The spinlock
 # peripheral is modeled as uncontended; allocation masks/program-space
 # bookkeeping and all ARM instructions are the actual sealed resident.
 native_path=Path(manifest['resident_elf_path'])
 assert hashlib.sha256(native_path.read_bytes()).hexdigest()==manifest['resident_elf_sha256']
 native=ELF(native_path)
 alloc=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
 for at,n in ((0x10000000,0x1c0000),(0x20000000,0x42000),(0x50200000,4096),(0x50300000,4096),(0xd0000000,4096)):
  alloc.mem_map(at,n)
 for seg in native.segments:
  if seg['data']:alloc.mem_write(seg['address'],seg['data'])
 def spin(uc,access,at,size,value,user):
  if 0xd0000100<=at<0xd0000180:uc.mem_write(at,pack(1))
 alloc.hook_add(UC_HOOK_MEM_READ,spin)
 def sdk(name,*args):
  for reg,value in zip((UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2),args):alloc.reg_write(reg,value)
  alloc.reg_write(UC_ARM_REG_SP,0x20041000);alloc.reg_write(UC_ARM_REG_LR,0x2003e001)
  alloc.reg_write(UC_ARM_REG_XPSR,0x1000000);alloc.reg_write(UC_ARM_REG_PRIMASK,0)
  alloc.emu_start(native.symbols[name]['value']|1,0x2003e000,count=100000)
  assert alloc.reg_read(UC_ARM_REG_PC)==0x2003e000 and not alloc.reg_read(UC_ARM_REG_PRIMASK)
  return alloc.reg_read(UC_ARM_REG_R0)
 sdk_cases=0
 assert [sdk('dma_claim_unused_channel',0) for _ in range(12)]==list(range(12));sdk_cases+=12
 assert sdk('dma_claim_unused_channel',0)==0xffffffff;sdk_cases+=1
 sdk('dma_channel_unclaim',5);assert sdk('dma_claim_unused_channel',0)==5;sdk_cases+=1
 for c in range(12):sdk('dma_channel_unclaim',c)
 assert [sdk('pio_claim_unused_sm',0x50200000,0) for _ in range(4)]==list(range(4));sdk_cases+=4
 assert sdk('pio_claim_unused_sm',0x50200000,0)==0xffffffff;sdk_cases+=1
 sdk('pio_sm_unclaim',0x50200000,2);assert sdk('pio_claim_unused_sm',0x50200000,0)==2;sdk_cases+=1
 for sm in range(4):sdk('pio_sm_unclaim',0x50200000,sm)
 program=0x20030000;instructions=program+16
 alloc.mem_write(instructions,struct.pack('<32H',*([0xa042]*32)))
 alloc.mem_write(program,struct.pack('<IBbBB',instructions,5,-1,0,0))
 offsets=[]
 for i in range(6):
  assert sdk('pio_can_add_program',0x50200000,program)==1
  offsets.append(sdk('pio_add_program',0x50200000,program));sdk_cases+=1
 assert sdk('pio_can_add_program',0x50200000,program)==0;sdk_cases+=1
 for at in offsets:sdk('pio_remove_program',0x50200000,program,at)
 alloc.mem_write(program,struct.pack('<IBbBB',instructions,32,-1,0,0))
 assert sdk('pio_can_add_program',0x50200000,program)==1
 at=sdk('pio_add_program',0x50200000,program);assert at==0;sdk_cases+=1
 assert sdk('pio_can_add_program',0x50200000,program)==0;sdk_cases+=1
 sdk('pio_remove_program',0x50200000,program,at)
 for borrowed,enabled,stuck,reset_stuck in ((0,1,0,0),(1,1,0,0),(0,0,0,0),(1,1,1,0),(1,1,0,1)):
  u=Uc(UC_ARCH_ARM,UC_MODE_MCLASS|UC_MODE_THUMB)
  for at,n in ((0x20000000,0x20000),(0x40000000,0x60000)):u.mem_map(at,n)
  for seg in pe.segments:
   if seg['data']:u.mem_write(seg['address'],seg['data'])
  def pw(at,v):u.mem_write(at,pack(v))
  def pr(at):return struct.unpack('<I',u.mem_read(at,4))[0]
  def sym(name):return pe.symbols[name]['value']
  pw(sym('pins_active'),1);pw(sym('uart_borrowed'),borrowed)
  pw(sym('i2c_before'),enabled);pw(sym('uart_before'),0x301)
  saved_gpio=[0x1f,0x1f,2,2];saved_pad=[0x58,0x58,0x50,0x58]
  offsets=[0,4,8,0x14,0x18,0x1c,0x20,0x30,0x38,0x3c,0x7c,0x88,0x8c,0x90,0x94,0xa0]
  saved_config=[0x165,0x1f,0x55,40,47,5000,7500,0,0,0,38,3,0,0,100,468]
  u.mem_write(sym('i2c_config_before'),struct.pack('<16I',*saved_config))
  u.mem_write(sym('gpio_before'),struct.pack('<4I',*saved_gpio))
  u.mem_write(sym('pad_before'),struct.pack('<4I',*saved_pad))
  for i in range(4):pw(0x40014004+8*(6+i),6);pw(0x4001c004+4*(6+i),0x48)
  pw(0x40038030,0 if borrowed else 0x301)
  timer=[0];reset_writes=[];latched=[True]
  def read(u,access,at,size,value,user):
   if at==0x40054028:timer[0]+=1;pw(at,timer[0])
   if at==0x4004809c:pw(at,0 if stuck else pr(0x4004806c)&1)
   if at==0x4000c008:pw(at,0 if reset_stuck else 16)
  def reset_write(uc,access,at,size,value,user):
   if at in (0x4000e000,0x4000f000):
    assert value==16,'Reset touched a peripheral other than I2C1';reset_writes.append(at)
    if at==0x4000e000:
     for off in offsets:pw(0x40048000+off,0)
     pw(0x4004806c,0)
    else:latched[0]=False
   assert not any(at<start+length and start<at+size for start,length in native_regions),'Restore modified resident state'
  u.hook_add(UC_HOOK_MEM_READ,read)
  u.hook_add(UC_HOOK_MEM_WRITE,reset_write)
  u.reg_write(UC_ARM_REG_SP,0x2001f000);u.reg_write(UC_ARM_REG_LR,0x2001e001)
  u.reg_write(UC_ARM_REG_XPSR,0x1000000)
  u.emu_start(sym('restore_pins')|1,0x2001e000,count=10000)
  assert u.reg_read(UC_ARM_REG_PC)==0x2001e000
  expected=(-47 if reset_stuck else -32 if stuck else 0)&0xffffffff
  assert u.reg_read(UC_ARM_REG_R0)==expected
  for i in range(4):assert pr(0x40014004+8*(6+i))==saved_gpio[i] and pr(0x4001c004+4*(6+i))==saved_pad[i]
  assert pr(0x40038030)==0x301 and pr(0x4004806c)==(0 if reset_stuck else enabled)
  assert reset_writes==[0x4000e000,0x4000f000]and not latched[0]
  if not reset_stuck:
   assert [pr(0x40048000+off)for off in offsets]==saved_config,'I2C configuration not restored exactly'
  assert timer[0]<=210,'Restore exceeded modeled finite wait cap'
  assert not pr(sym('pins_active')) and not pr(sym('uart_borrowed'))
  pico_checks+=1
 result=dict(status='PASS',physical_io=False,hardware_timing_measured=False,relocated_ARM_cases=len(passed),
  faults=failures,wait_cancellations=3,invalid_lengths=5,read_only_identity_crc='3BE158B4',
  pico_restore_cases=pico_checks,identity_guard_cases=identity_cases,pio_resource_guard_cases=pio_cases,
  DBGMCU_zero_with_matching_body_accepted=True,actual_resident_sdk_allocator_cases=sdk_cases,idle_fence_cases=fence_results,
  full_take_pins_logical_cases=logical_results,
  native_health_boundary_cases=health_cases,
  m3_read_only_observation_cases=m3_observation_cases,
  module_sha256=hashlib.sha256(package).hexdigest(),old_restore_latched_BUSY_reproduced_in_model=True,
  pico_app_sha256=hashlib.sha256((a.kit/'app/FASTLINK.APP').read_bytes()).hexdigest(),
  sender_reference_only=a.sender_kit is not None,
  scope='actual Thumb-2 module and Pico restore; modeled MMIO/clock/DMA; independent bit-stream decoder')
 output=a.output or a.kit/('host-shared-test.json'if a.sender_kit else'host-test.json')
 output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
