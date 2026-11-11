"""Execute actual M0+ UART-adapter code with modeled RP2040 registers."""
import json,struct
from arm_execution import Target,B
from unicorn import UC_HOOK_MEM_WRITE
OUT=B/'southbridge-runtime/pico-probe'
t=Target(OUT/'pico-uart.elf',mmio=True);u=t.u;u.mem_map(0x40030000,0x10000)
def read(a):return struct.unpack('<I',u.mem_read(a,4))[0]
def write(a,v):u.mem_write(a,struct.pack('<I',v))
UART=0x40038000;RESET=0x4000c000;GPIO=0x40014044;PAD=0x4001c024
writes=[]
def model(uc,access,address,size,value,unused):
 if 0x40000000<=address<0x50000000:
  writes.append((address,value))
  if address==RESET+0x3000:
   write(RESET,read(RESET)&~value);write(RESET+8,read(RESET+8)|value)
  elif address==RESET+0x2000:write(RESET,read(RESET)|value)
u.hook_add(UC_HOOK_MEM_WRITE,model)
write(RESET,(1<<23)|0x123);write(GPIO,31);write(GPIO+8,31);write(PAD,0x56);write(PAD+4,0x16)
assert t.call('harness_begin',125000000,2250000)==0 and not writes
write(UART+0x30,1);write(RESET,0x123)
assert t.call('harness_begin',48000000,2250000)==0 and not writes
write(UART+0x30,0);write(GPIO,2)
assert t.call('harness_begin',48000000,2250000)==0 and not writes
write(GPIO,31);write(RESET,(1<<23)|0x123)
assert t.call('harness_begin',48000000,2250000)==1
assert read(UART+0x24)==1 and read(UART+0x28)==21 and read(UART+0x2c)==0x70 and read(UART+0x30)==0x301
assert read(GPIO)==2 and read(GPIO+8)==2 and read(RESET)==0x123
assert t.call('harness_baud')==2258823
u.mem_write(t.scratch,b'ABC');assert t.call('harness_send',t.scratch,3,100)==1
assert [v for a,v in writes if a==UART][-3:]==[65,66,67]
write(UART+0x18,32);assert t.call('harness_send',t.scratch,1,8)==0
write(UART+0x18,0);write(UART,0xa5);assert t.call('harness_read',100)==0xa5
write(UART,0x101);assert t.call('harness_read',100)==0xfffffffe and t.call('harness_errors')==1
write(UART+0x18,16);assert t.call('harness_read',8)==0xffffffff
write(UART+0x18,0);t.call('harness_end')
assert read(GPIO)==31 and read(GPIO+8)==31 and read(PAD)==0x56 and read(PAD+4)==0x16
assert read(RESET)==(1<<23)|0x123 and read(UART+0x30)==0
allowed={UART+i for i in [0,4,0x24,0x28,0x2c,0x30,0x34,0x38,0x44,0x48]}
allowed|={GPIO,GPIO+8,PAD,PAD+4,RESET+0x2000,RESET+0x3000}
assert all(a in allowed for a,v in writes)
report=dict(status='PICO_M0_UART_MMIO_PASS',physical_io=False,wrong_clock_and_busy_owner_refused=True,
            tx_rx_and_timeouts=True,rx_error_detected=True,pins_pads_uart_reset_restored=True,
            only_uart1_gpio8_9_changed=True,dma_uart0_i2c_untouched=True,actual_baud=2258823)
(OUT/'uart-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
