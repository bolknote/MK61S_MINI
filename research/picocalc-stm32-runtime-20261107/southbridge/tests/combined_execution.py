"""Execute the port with modeled F103 MMIO, including the UART wire path."""
from pathlib import Path
import binascii,json,random,struct
from arm_execution import vectors
from unicorn import UC_HOOK_MEM_WRITE,UC_HOOK_MEM_READ,UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0
Target=vectors.Target;B=vectors.B
DMA=0x40020000;CH2=DMA+0x1c;CH3=DMA+0x30;UART=0x40004800
RCC=0x40021000;FLASH=0x40022000;TIM1=0x40012c00;TIM2=0x40000000;TIM3=0x40000400
GPIOC=0x40011000;AFIO=0x40010000
class Transport(Target):
 def __init__(self):
  super().__init__(B/'combined-harness/combined.elf',mmio=True)
  self.produced=0;self.total_received=0;self.rx=self.call('harness_rx_buffer');self.native_calls=0
  self.max_calls_per_poll=0
  self.entry=None
  def write_mmio(uc,access,address,size,value,unused):
   if address==DMA+4:
    clear=value
    for ch in range(1,8):
     if value&(1<<(4*(ch-1))):clear|=15<<(4*(ch-1))
    self.write(DMA,self.read(DMA)&~clear)
  def read_mmio(uc,access,address,size,value,unused):
   # Ready bits and clock-source status are read-only hardware side effects.
   if address==RCC:
    v=self.read(RCC);v=(v&~((1<<17)|(1<<25)))|((v&((1<<16)|(1<<24)))<<1);self.write(RCC,v)
   elif address==RCC+4:
    v=self.read(address);self.write(address,(v&~12)|((v&3)<<2))
   elif address==RCC+0x20:
    v=self.read(address);self.write(address,(v&~2)|((v&1)<<1))
   elif address==RCC+0x24:
    v=self.read(address);self.write(address,(v&~2)|((v&1)<<1))
  def call_native(uc,address,size,unused):
   if self.entry is not None and address==self.entry:self.native_calls+=1
  self.u.hook_add(UC_HOOK_MEM_WRITE,write_mmio)
  self.u.hook_add(UC_HOOK_MEM_READ,read_mmio)
  self.u.hook_add(UC_HOOK_CODE,call_native)
 def read(self,at):return struct.unpack('<I',self.u.mem_read(at,4))[0]
 def write(self,at,value):self.u.mem_write(at,struct.pack('<I',value&0xffffffff))
 def poll(self):
  before=self.native_calls;result=self.call('harness_poll')
  count=self.native_calls-before;self.max_calls_per_poll=max(self.max_calls_per_poll,count)
  assert count<=1,'More than one cooperative call before returning to the keyboard loop'
  return result
 def deliver(self,frame):
  assert self.read(CH3)&1
  for value in frame:
   self.u.mem_write(self.rx+self.produced%512,bytes([value]));self.produced+=1;self.total_received+=1
   self.write(CH3+4,512-self.produced%512)
   if self.produced%512==0:
    self.write(DMA,self.read(DMA)|(1<<9));self.call('DMA1_Channel3_IRQHandler')
 def send(self,frame):
  self.deliver(frame)
  for _ in range(24):
   self.poll()
   if self.read(CH2)&1 and self.read(CH2+4):
    n=self.read(CH2+4);at=self.read(CH2+12)
    assert 0<n<=272
    response=bytes(self.u.mem_read(at,n))
    # Keep the DMA outstanding while jobs and I2C get another main-loop turn.
    self.poll();assert bytes(self.u.mem_read(at,n))==response
    assert self.call('harness_i2c',0x0b,0,0)==0x0bad
    assert self.call('stm3_uart_tx_start',self.scratch,1)==0
    assert self.read(CH2+12)==at
    self.write(CH2+4,0);self.write(DMA,self.read(DMA)|(1<<5))
    return response
  return b''
 def load(self,package,expected=0):
  result=super().load(package,expected)
  if not expected:
   base=self.elf.symbols['coproc']['value']+self.call('harness_arena_offset')
   self.entry=base+(struct.unpack_from('<I',package,24)[0]&~1)
   self.module_range=(base,base+struct.unpack_from('<I',package,16)[0])
  return result
 # Target.load asks for this name; the combined bridge uses its real arena.
 def call(self,name,*args):
  if name=='harness_module_base':
   return self.elf.symbols['coproc']['value']+super().call('harness_arena_offset')
  return super().call(name,*args)
def main():
 t=Transport()
 assert t.read(UART+8)==16 and t.read(CH3+4)==512
 # Execute the genuine clock function, including re-entry after PLL was active.
 for _ in range(2):
  assert t.call('harness_clock72')==72000000
  cfgr=t.read(RCC+4)
  assert cfgr&3==2 and (cfgr>>2)&3==2 and (cfgr>>4)&15==0
  assert (cfgr>>8)&7==4 and (cfgr>>11)&7==0
  assert (cfgr>>18)&15==7 and cfgr&(1<<16) and not(cfgr&(1<<17))
  assert t.read(FLASH)&7==2 and t.read(FLASH)&(1<<4)
 # Microsecond snapshots around a TIM2 update must count it exactly once.
 t.call('harness_set_clock',234);t.write(TIM2+0x24,999);t.write(TIM2+0x10,0)
 assert t.call('harness_micros')==234999
 t.write(TIM2+0x24,3);t.write(TIM2+0x10,1);assert t.call('harness_micros')==235003
 t.call('harness_set_clock',235);t.write(TIM2+0x10,0);assert t.call('harness_micros')==235003
 # Both raw brightness registers cover all256 values, with exact wire echo.
 for reg,timer,ccr in [(5,TIM1,0x34),(10,TIM3,0x3c)]:
  previous=-1
  for value in range(256):
   assert t.call('harness_i2c',reg,1,value)==reg*256+value
   assert t.call('harness_i2c',reg,0,0)==reg*256+value
   actual=t.read(timer+ccr);expected=((t.read(timer+0x2c)+1)*value+127)//255
   assert actual==expected and actual>=previous;previous=actual
 t.call('harness_i2c',5,1,32);t.call('harness_i2c',10,1,0)
 assert t.call('harness_backlight_cycle',0)==0x3000
 assert t.call('harness_backlight_cycle',1)==0x2000
 assert t.call('harness_backlight_cycle',2)==0x2020
 t.call('harness_backlight_off');assert t.read(TIM1+0x34)==0 and t.read(TIM3+0x3c)==0
 t.call('harness_backlight_on');assert t.read(TIM1+0x34)>0 and t.read(TIM3+0x3c)>0
 # Genuine FIFO and I2C callbacks retain stock {state,key} ordering.
 for i in range(31):assert t.call('harness_enqueue',1,i+32)==1
 assert t.call('harness_enqueue',1,250)==0
 for i in range(31):assert t.call('harness_i2c',9,0,0)==0x100+i+32
 assert t.call('harness_i2c',9,0,0)==0
 assert t.call('harness_i2c',3,1,255)==0x300 # No PC10 IRQ write in UART mode.
 t.call('harness_set_clock',300);assert t.call('harness_storage_idle')==1
 package=(B/'module/q4_dot.s3m').read_bytes();t.request(1);module=t.load(package)
 assert t.call('harness_storage_idle')==0
 rng=random.Random(620103);rows_checked=0
 for test in range(8):
  rows=2+2*test;xs=[rng.randint(-32768,32767)for _ in range(32)]
  weights=[[rng.randint(-8,7)for _ in range(32)]for _ in range(rows)]
  raw=struct.pack('<III32h',0x31544451,rows,32,*xs)+bytes((w[i]+8)|((w[i+1]+8)<<4)for w in weights for i in range(0,32,2))
  for at in range(0,len(raw),252):t.request(5,struct.pack('<I',at)+raw[at:at+252])
  job=struct.unpack('<I',t.request(6,struct.pack('<III',module,len(raw),1000)))[0]
  if test==0:assert t.send(t.last_frame)==t.last_reply
  for _ in range(20):
   status=struct.unpack('<7I',t.request(7,struct.pack('<I',job)))
   if status[1]==4:break
  assert status[1:3]==(4,0)
  out=t.request(8,struct.pack('<III',job,0,8+4*rows))
  assert struct.unpack_from('<II',out)==(rows,test+1)
  assert list(struct.unpack_from('<'+'i'*rows,out,8))==[sum(x*w for x,w in zip(xs,row))for row in weights]
  rows_checked+=rows
  assert t.call('harness_enqueue',1,27)==1 and t.call('harness_i2c',9,0,0)==0x11b
 # Power-off aborts transport and module without calling untrusted FINI.
 calls=t.native_calls;t.call('harness_suspend');assert t.native_calls==calls
 assert not t.read(CH2)&1 and not t.read(CH3)&1 and t.read(UART+0xc)==0
 assert t.read(GPIOC+4)&0xff00==0x4400
 assert t.call('stm3_uart_begin',4000000)==0
 t.call('harness_resume');t.produced=0;assert t.read(UART+8)==16
 assert struct.unpack_from('<I',t.request(1),16)[0]==0
 # Option-byte policy: ordinary SLEEP fallback or STOP with existing permission.
 t.call('harness_suspend');t.write(FLASH+0x1c,0)
 assert t.call('harness_sleep')==1
 t.write(FLASH+0x1c,1<<3);assert t.call('harness_sleep')==0x10001
 unused=t.call('coproc_stack_unused');assert 0<unused<=4096
 report=dict(status='COMBINED_ARM_MMIO_PASS',physical_io=False,physical_timing=False,
             clock72_and_reentry=True,tim2_pending_update_counted_once=True,
             backlight_wire_values_tested=512,fifo_events=31,keyboard_reads_during_uart_jobs=True,
             q4_dot_rows=rows_checked,uart_bytes_received=t.total_received,duplicate_start_idempotent=True,
             max_module_invocations_per_poll=t.max_calls_per_poll,zero_copy_tx_lifetime=True,
             no_fini_on_power_off=True,sleep_option_byte_fallback=True,
             modeled_stack_unused_bytes=unused,stack_value_is_hardware_measurement=False)
 (B/'combined-execution.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
