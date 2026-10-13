#!/usr/bin/env python3
"""Execute the owned production USB bridge against an OTG register/stack model."""
import argparse,struct
from pathlib import Path
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_CODE
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf
p=argparse.ArgumentParser();p.add_argument('elf',type=Path);a=p.parse_args();e=Elf(a.elf)
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
for base,size in [(0x08000000,0x100000),(0x20000000,0x20000),(0x40000000,0x30000),(0x50000000,0x20000),(0xE000E000,0x2000)]:u.mem_map(base,size)
u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000)
u.reg_write(UC_ARM_REG_FPEXC,1<<30)
e.load(u)
stop=0x080FF000;u.mem_write(stop,b'\x70\x47');sp=0x2001FFF0
USB=0x50000000;D=USB+0x800;IN=USB+0x900;OUT=USB+0xB00
FIFO=USB+0x1000
queue=[];rx_words=[];tx_words=[];events=[];ticks=0;rearm_in=None
uw=[v for k,v in e.symbols.items() if k=='uwTick' or k.startswith('uwTick.')][0]
def get(addr):return struct.unpack('<I',u.mem_read(addr,4))[0]
def put(addr,value):u.mem_write(addr,struct.pack('<I',value&0xffffffff))
def memory(uc,access,addr,size,value,_):
 global ticks
 if access==16:
  if addr==uw:ticks+=1;put(addr,ticks)
  if addr==USB+0x10:put(addr,0x80000000) # idle AHB, self-clearing core/FIFO reset.
  if addr==USB+0x20:
   item=queue.pop(0) if queue else 0;put(addr,item)
   if not queue:put(USB+0x14,get(USB+0x14)&~(1<<4))
  if addr==FIFO:
   assert rx_words,'FIFO overread';put(addr,rx_words.pop(0))
 elif access==17:
  if addr==USB+0x14 or addr==USB+0x04 or any(addr==b+n*32+8 for b in [IN,OUT] for n in range(4)):
   put(addr,get(addr)&~value)
  if FIFO<=addr<FIFO+4*0x1000 and (addr-FIFO)%0x1000==0:tx_words.append((addr,value))
callbacks={}
for name in ['USBD_LL_DataInStage','USBD_LL_DataOutStage','__wrap_USBD_LL_SetupStage','__wrap_USBD_LL_Reset','USBD_LL_SetSpeed','__wrap_USBD_LL_Suspend','__wrap_USBD_LL_Resume','USBD_LL_SOF','__wrap_USBD_LL_DevConnected','__wrap_USBD_LL_DevDisconnected','USBD_SystemClockConfigFromResume']:
 if name in e.symbols:callbacks[e.symbols[name]&~1]=name

# MMIO writes occur after a Unicorn memory hook; restore W1C values before the next instruction.
w1c={}
def write_hook(uc,access,addr,size,value,_):
 if addr==USB+0x14 or addr==USB+0x04 or any(addr==b+n*32+8 for b in [IN,OUT] for n in range(4)):w1c[addr]=get(addr)&~value
def code(uc,address,size,_):
 global rearm_in
 for addr,value in list(w1c.items()):put(addr,value)
 w1c.clear()
 name=callbacks.get(address)
 if name:
  events.append((name,uc.reg_read(UC_ARM_REG_R0),uc.reg_read(UC_ARM_REG_R1),uc.reg_read(UC_ARM_REG_R2)))
  if name=='USBD_LL_DataInStage' and rearm_in is not None:
   # Model a CDC callback queuing the next transfer while the IRQ is active.
   data,length=rearm_in;rearm_in=None
   uc.reg_write(UC_ARM_REG_R1,0x82);uc.reg_write(UC_ARM_REG_R2,data);uc.reg_write(UC_ARM_REG_R3,length)
   uc.reg_write(UC_ARM_REG_PC,e.symbols['USBD_LL_Transmit']|1)
  else:
   uc.reg_write(UC_ARM_REG_R0,0);uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_MEM_READ,memory);u.hook_add(UC_HOOK_MEM_WRITE,memory);u.hook_add(UC_HOOK_MEM_WRITE,write_hook);u.hook_add(UC_HOOK_CODE,code)
def call(name,*args):
 u.reg_write(UC_ARM_REG_XPSR,0x01000000)
 for reg in [UC_ARM_REG_R4,UC_ARM_REG_R5,UC_ARM_REG_R6,UC_ARM_REG_R7,UC_ARM_REG_R8,UC_ARM_REG_R9,UC_ARM_REG_R10,UC_ARM_REG_R11]:u.reg_write(reg,0x12340000+reg)
 for reg,value in [(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_R0,0),(UC_ARM_REG_R1,0),(UC_ARM_REG_R2,0),(UC_ARM_REG_R3,0)]:u.reg_write(reg,value)
 for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,value)
 if len(args)>4:u.mem_write(sp,struct.pack('<I',args[4]))
 u.ctl_remove_cache(0x08000000,0x08100000)
 try:u.emu_start(e.symbols[name]|1,stop,timeout=5000000,count=5000000)
 except Exception:
  print('ARM failure',name,hex(u.reg_read(UC_ARM_REG_PC)),bytes(u.mem_read(u.reg_read(UC_ARM_REG_PC),8)).hex(),[hex(u.reg_read(r)) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3,UC_ARM_REG_R5,UC_ARM_REG_SP]]);raise
 assert u.reg_read(UC_ARM_REG_PC)==stop,(name,'failed return',hex(u.reg_read(UC_ARM_REG_PC)))
 assert u.reg_read(UC_ARM_REG_SP)==sp
 return u.reg_read(UC_ARM_REG_R0)
# Power-up/reset register model; application/middleware calls are mocked.
put(USB+0x10,0x80000000);put(USB+0x40,0x4F54281A)
assert call('USBD_LL_Init',0x20016000)==0
for ep,kind,mps in [(0,0,64),(0x80,0,64),(1,2,64),(0x81,2,64),(0x82,2,64),(0x83,3,8)]:assert call('USBD_LL_OpenEP',0x20016000,ep,kind,mps)==0
assert call('USBD_LL_OpenEP',0x20016000,0x8F,2,64)!=0
# Short unaligned transmission must not read canaries outside the requested bytes.
src=0x20017001;u.mem_write(src-1,b'\xEE'+b'abcde'+b'\xDD'*4)
assert call('USBD_LL_Transmit',0x20016000,0x82,src,5)==0
put(IN+2*32+0x18,16);put(D+0x18,1<<2);put(D+0x1C,get(D+0x1C)|(1<<2));put(D+0x34,1<<2);put(D+0x10,1);put(IN+2*32+8,1<<7);put(USB+0x18,(1<<18)|(1<<4));put(USB+0x14,1<<18)
call('OTG_FS_IRQHandler');assert tx_words[-2:]==[(FIFO+2*0x1000,0x64636261),(FIFO+2*0x1000,0x65)],tx_words
put(IN+2*32+8,1);put(USB+0x14,1<<18);call('OTG_FS_IRQHandler');assert any(x[0]=='USBD_LL_DataInStage' for x in events)
# Queueing IN from completion must survive the current IRQ's mask/flag cleanup.
next_data=0x20017100;u.mem_write(next_data,b'xy');rearm_in=(next_data,2)
put(IN+2*32+8,1);put(USB+0x14,1<<18);call('OTG_FS_IRQHandler')
assert get(D+0x34)&(1<<2)
put(IN+2*32+8,1<<7);put(USB+0x14,1<<18);call('OTG_FS_IRQHandler')
assert tx_words[-1]==(FIFO+2*0x1000,0x7978)
# Oversized host OUT packet: report all received bytes, but copy only buffer capacity.
dest=0x20017201;u.mem_write(dest-1,b'\xCD'*20)
assert call('USBD_LL_PrepareReceive',0x20016000,1,dest,5)==0
queue.append(1|(8<<4)|(2<<17));rx_words.extend([0x64636261,0x68676665]);put(USB+0x14,1<<4);call('OTG_FS_IRQHandler')
assert bytes(u.mem_read(dest-1,12))==b'\xCDabcde'+b'\xCD'*6
assert call('USBD_LL_GetRxDataSize',0x20016000,1)==8
# Drain queued RX payloads before dispatching a simultaneous OUT completion.
assert call('USBD_LL_PrepareReceive',0x20016000,1,dest,8)==0
queue.extend([1|(4<<4)|(2<<17),1|(4<<4)|(2<<17)])
rx_words.extend([0x34333231,0x38373635])
put(D+0x18,1<<17);put(D+0x14,1);put(OUT+32+8,1)
put(USB+0x18,get(USB+0x18)|(1<<19));put(USB+0x14,(1<<4)|(1<<19))
call('OTG_FS_IRQHandler')
assert not queue and not rx_words and bytes(u.mem_read(dest,8))==b'12345678'
assert call('USBD_LL_GetRxDataSize',0x20016000,1)==8
assert any(x[0]=='USBD_LL_DataOutStage' and x[2]==1 for x in events)
# Standard request guards must reject unsupported endpoint numbers before middleware arrays.
req=0x20017400
for index in [4,15,0x84,0x8F,0x100,0x70]:
 u.mem_write(req,struct.pack('<BBHHH',0x82,0,0,index,2))
 assert call('USBD_StdEPReq',0x20016000,req)==3
# Bus reset primes control setup, enumeration reports full-speed reset exactly once.
put(USB+0x18,get(USB+0x18)|(1<<12)|(1<<13)|(1<<11)|(1<<31));put(USB+0x14,1<<12);call('OTG_FS_IRQHandler')
assert get(D+0x1C)==0x10001 and (get(D)&0x7F0)==0
put(USB+0x14,1<<13);call('OTG_FS_IRQHandler')
assert sum(x[0]=='__wrap_USBD_LL_Reset' for x in events)==1
put(D+8,1);put(USB+0x14,1<<11);call('OTG_FS_IRQHandler')
assert any(x[0]=='__wrap_USBD_LL_Suspend' for x in events)
assert get(USB+0xE00)&1
put(USB+0x14,1<<31);call('OTG_FS_IRQHandler')
assert any(x[0]=='__wrap_USBD_LL_Resume' for x in events) and not get(USB+0xE00)&1
# Setup payload in the FIFO and STUP in the same IRQ must reach middleware intact.
setup_data=struct.pack('<BBHHH',0x80,6,0x100,0,18)
queue.append((8<<4)|(6<<17));rx_words.extend(struct.unpack('<II',setup_data))
put(D+0x18,1<<16);put(OUT+8,1<<3);put(USB+0x14,(1<<4)|(1<<19))
call('OTG_FS_IRQHandler')
setup_event=[x for x in events if x[0]=='__wrap_USBD_LL_SetupStage'][-1]
assert bytes(u.mem_read(setup_event[2],8))==setup_data
# Cleanup/reinitialization preserves primask and starts a clean controller context.
assert call('USBD_LL_Stop',0x20016000)==0
assert call('USBD_LL_DeInit',0x20016000)==0
assert call('USBD_LL_Init',0x20016000)==0 and call('USBD_LL_Start',0x20016000)==0
# DMA/HS/ISO are absent; the shipping path uses only bounded device packets.
print('Owned OTG FS ARM model: init, endpoint bounds, W1C, TX/RX tails, rearm, RX drain/setup, request guards, reset, suspend/resume and reinit PASS')
