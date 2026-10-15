#!/usr/bin/env python3
"""Exercise the actual linked CDC class with protocol/MMIO boundaries mocked."""
import argparse, struct
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import *
from run_portable_system_arm_tests import Elf
p=argparse.ArgumentParser();p.add_argument('elf',type=Path);a=p.parse_args();e=Elf(a.elf)
u=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS);u.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M4)
for base,size in [(0x08000000,0x100000),(0x20000000,0x20000),(0x40000000,0x30000),(0x50000000,0x20000),(0xE000E000,0x2000)]:u.mem_map(base,size)
u.reg_write(UC_ARM_REG_C1_C0_2,0xF00000);u.reg_write(UC_ARM_REG_FPEXC,1<<30);e.load(u)
stop=0x080FF000;u.mem_write(stop,b'\x70\x47');sp=0x2001FFF0
mock_names=['USBD_LL_Init','USBD_LL_Start','USBD_LL_Stop','USBD_LL_DeInit','USBD_LL_OpenEP','USBD_LL_CloseEP',
 'USBD_LL_PrepareReceive','USBD_LL_Transmit','USBD_LL_GetRxDataSize','USBD_LL_SetUSBAddress',
 'USBD_CtlSendData','USBD_CtlPrepareRx','USBD_CtlSendStatus','USBD_CtlError']
mocks={value&~1:name for name,value in e.symbols.items() if any(name==n or name.startswith(n+'.') for n in mock_names)}
events=[];rx_size=0;rx_buffer=None
rx_setters={value&~1 for name,value in e.symbols.items() if name=='USBD_CDC_SetRxBuffer' or name.startswith('USBD_CDC_SetRxBuffer.')}
assert rx_setters, 'real RX buffer setter is missing'
# Read the ELF symbol size instead of assuming the historical C struct layout.
cdc_size=None
for section in e.sections:
 if section[1]!=2:continue
 strings=e.sections[section[6]];names=e.data[strings[4]:strings[4]+strings[5]]
 for off in range(section[4],section[4]+section[5],section[9]):
  name,value,size,info,other,index=struct.unpack_from('<IIIBBH',e.data,off)
  if names[name:names.find(b'\0',name)]==b'_hcdc':cdc_size=size
assert cdc_size in (28,36), cdc_size

def hook(uc,address,size,unused):
 global rx_buffer
 if address in rx_setters:rx_buffer=uc.reg_read(UC_ARM_REG_R1)
 name=mocks.get(address)
 if name:
  args=[uc.reg_read(reg) for reg in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
  events.append((name.split('.')[0],args))
  if name.startswith(('USBD_CtlSendData','USBD_CtlPrepareRx')):
   assert args[2]<=67,(name,args)
   if args[2]:uc.mem_read(args[1],args[2])
  uc.reg_write(UC_ARM_REG_R0,rx_size if name=='USBD_LL_GetRxDataSize' else 0)
  uc.reg_write(UC_ARM_REG_PC,uc.reg_read(UC_ARM_REG_LR))
u.hook_add(UC_HOOK_CODE,hook)

def resolve(name):
 if name in e.symbols:return e.symbols[name]
 matches=[v for n,v in e.symbols.items() if n.startswith(name+'.')]
 assert len(matches)==1,(name,len(matches));return matches[0]

def call(name,*args):
 u.reg_write(UC_ARM_REG_XPSR,0x01000000)
 for reg,value in [(UC_ARM_REG_SP,sp),(UC_ARM_REG_LR,stop|1),(UC_ARM_REG_R0,0),(UC_ARM_REG_R1,0),(UC_ARM_REG_R2,0),(UC_ARM_REG_R3,0)]:u.reg_write(reg,value)
 for reg,value in zip([UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3],args):u.reg_write(reg,value)
 u.emu_start(resolve(name)|1,stop,timeout=5000000,count=1000000)
 assert u.reg_read(UC_ARM_REG_PC)==stop and u.reg_read(UC_ARM_REG_SP)==sp,(name,hex(u.reg_read(UC_ARM_REG_PC)))
 return u.reg_read(UC_ARM_REG_R0)

d=e.symbols['hUSBD_Device_CDC'];r=0x20018000
u.reg_write(UC_ARM_REG_PRIMASK,1)
call('CDC_continue_transmit');assert call('CDC_resume_receive')==0
assert u.reg_read(UC_ARM_REG_PRIMASK)==1
u.reg_write(UC_ARM_REG_PRIMASK,0)
call('CDC_init');call('USBD_LL_SetSpeed',d,1)
def standard(bm,request,value,index,length):
 u.mem_write(r,struct.pack('<BBHHH',bm,request,value,index,length))
 return call('USBD_StdDevReq',d,r)
standard(0,5,7,0,0);standard(0,9,1,0,0)
opened=[args[1:] for n,args in events if n=='USBD_LL_OpenEP'];assert sorted(opened)==[[1,2,64],[0x82,2,64],[0x83,3,8]],opened

def setup(bm,request,value=0,index=0,length=0):
 events.clear();u.mem_write(r,struct.pack('<BBHHH',bm,request,value,index,length))
 return call('cdc_setup',d,r)
def reply():
 records=[args for name,args in events if name=='USBD_CtlSendData'];assert len(records)==1,events
 args=records[0];return args[1],bytes(u.mem_read(args[1],args[2]))
assert setup(0xA1,0x21,length=7)==0
address,data=reply();assert data==bytes([0,0xC2,1,0,0,0,8]),data
assert address==e.symbols['_hcdc']
for length in [0,1,2,6,8,64,255,65535]:
 before=bytes(u.mem_read(e.symbols['_hcdc'],cdc_size))
 assert setup(0x21,0x20,length=length)!=0
 assert not any(name=='USBD_CtlPrepareRx' for name,args in events)
 assert bytes(u.mem_read(e.symbols['_hcdc'],cdc_size))==before
for bm,request,value,index,length in [(0xA1,0x20,0,0,7),(0x21,0x20,1,0,7),(0x21,0x20,0,1,7),(0x21,0x22,0,0,1),(0xA1,0x21,0,2,7),(0xA1,0x00,0,0,65535)]:
 assert setup(bm,request,value,index,length)!=0
assert setup(0x21,0x20,length=7)==0
prepared=[args for name,args in events if name=='USBD_CtlPrepareRx'];assert prepared[0][1:3]==[address,7]
u.mem_write(address,bytes([0,0x84,3,0,0,0,8]));rx_size=7
assert call('cdc_rx_ready',d)==0
assert setup(0x21,0x20,length=7)==0
rx_size=6;assert call('cdc_rx_ready',d)!=0
assert setup(0xA1,0x21,length=65535)==0 and reply()[1]==bytes([0,0x84,3,0,0,0,8])
assert setup(0x81,0,index=1,length=2)==0
address,status=reply();assert status==bytes(2) and address==e.symbols['_hcdc']
assert setup(0x81,10,index=1,length=1)==0 and reply()[1]==bytes(1)
assert setup(0x01,11,value=1,index=1)!=0
assert setup(0x21,0x22,value=3)==0 and call('CDC_connected')==1
# Configuration is immutable, qualifier/other-speed requests stall on FS.
events.clear();standard(0x80,6,0x0200,0,255)
args=[a for n,a in events if n=='USBD_CtlSendData'][-1];assert 0x08000000<=args[1]<0x08100000 and args[2]==67
configuration=bytes(u.mem_read(args[1],67));assert configuration[:4]==bytes([9,2,67,0])
for descriptor in [0x0600,0x0700]:
 events.clear();standard(0x80,6,descriptor,0,255);assert any(n=='USBD_CtlError' for n,args in events)
# Exact 64/128-byte packets need one ZLP before completion; 63/65 do not.
buffer=0x20019000;u.mem_write(buffer,bytes(range(128)))
for length in [0,1,63,64,65,128,65535,65536,0x10000+64]:
 assert call('USBD_CDC_SetTxBuffer',d,buffer,length)==0
 events.clear();assert call('USBD_CDC_TransmitPacket',d)==0
 transfer=[args for name,args in events if name=='USBD_LL_Transmit'];assert len(transfer)==1 and transfer[0][1:]==[0x82,buffer,length],transfer
 assert call('USBD_CDC_TransmitPacket',d)==1 # busy until final completion
 events.clear();assert call('cdc_data_in',d,2)==0
 zeroes=[args for n,args in events if n=='USBD_LL_Transmit' and args[3]==0]
 if length and length%64==0:
  assert len(zeroes)==1 and call('USBD_CDC_TransmitPacket',d)==1
  events.clear();assert call('cdc_data_in',d,2)==0
  assert not any(n=='USBD_LL_Transmit' for n,args in events)
 else:assert not zeroes
assert call('cdc_data_in',d,15)!=0
# Full-width malformed lengths must fail before consuming or rearming RX.
for oversized in [65,65535,65536,0xffffffff]:
 rx_size=oversized;events.clear()
 assert call('cdc_data_out',d,1)!=0
 assert not any(n=='USBD_LL_PrepareReceive' for n,args in events)
rx_size=64
# Fill the real RX queue, require NAK, then drain/rearm without byte loss.
h=e.symbols['_hcdc'];received=[]
for first in [0,64]:
 pointer=rx_buffer;assert pointer is not None
 u.mem_write(pointer,bytes(range(first,first+64)));rx_size=64
 events.clear();assert call('cdc_data_out',d,1)==0
 if first==64:assert not any(n=='USBD_LL_PrepareReceive' for n,args in events)
received.append(call('CDC_ReceiveQueue_Dequeue',resolve('ReceiveQueue')));assert received==[0]
assert call('CDC_resume_receive')==1
pointer=rx_buffer;assert pointer is not None;u.mem_write(pointer,bytes(range(128,192)))
events.clear();assert call('cdc_data_out',d,1)==0
assert not any(n=='USBD_LL_PrepareReceive' for n,args in events)
for _ in range(191):
 received.append(call('CDC_ReceiveQueue_Dequeue',resolve('ReceiveQueue')));call('CDC_resume_receive')
assert received==list(range(192)) and call('CDC_ReceiveQueue_Dequeue',resolve('ReceiveQueue'))==0xFFFFFFFF
call('CDC_deInit');call('CDC_continue_transmit');assert call('CDC_resume_receive')==0
assert u.reg_read(UC_ARM_REG_PRIMASK)==0
print('Owned CDC production ARM model: FS enumeration, readonly descriptor, ACM bounds, persistent EP0 replies and ZLP completion PASS')
