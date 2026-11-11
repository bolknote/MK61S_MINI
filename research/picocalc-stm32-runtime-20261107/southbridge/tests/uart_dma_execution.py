"""Execute our ARM DMA driver with modeled STM32 registers, no board attached."""
from pathlib import Path
import json,struct
from arm_execution import vectors
Target=vectors.Target;B=vectors.B
from unicorn import UC_HOOK_MEM_WRITE

def main():
 t=Target(B/'uart-harness/uart.elf',mmio=True);u=t.u
 def read(at):return struct.unpack('<I',u.mem_read(at,4))[0]
 def write(at,value):u.mem_write(at,struct.pack('<I',value))
 DMA=0x40020000;CH2=DMA+0x1c;CH3=DMA+0x30;USART=0x40004800;GPIOC=0x40011000;AFIO=0x40010000;RCC=0x40021000
 # Model only documented W1C side effects; data movement is supplied by the test.
 def peripheral_write(uc,access,address,size,value,unused):
  if address==DMA+4:
   clear=value
   for channel in range(1,8):
    if value&(1<<(4*(channel-1))):clear|=15<<(4*(channel-1))
   write(DMA,read(DMA)&~clear)
  elif address==GPIOC+0x10:write(GPIOC+0xc,(read(GPIOC+0xc)|(value&65535))&~(value>>16))
 u.hook_add(UC_HOOK_MEM_WRITE,peripheral_write)
 write(GPIOC+4,0xa5a5a5a5);write(AFIO+4,0x04001000);write(RCC+0x1c,0x00600000)
 assert t.call('stm3_uart_begin',32000000)==0 and read(GPIOC+4)==0xa5a5a5a5
 write(CH2,1);assert t.call('stm3_uart_begin',36000000)==0 and read(GPIOC+4)==0xa5a5a5a5;write(CH2,0)
 assert t.call('stm3_uart_begin',36000000)==1
 assert read(USART+8)==16 and read(USART+0xc)==0x200c and read(USART+0x10)==0 and read(USART+0x14)==0xc0
 assert read(GPIOC+4)==(0xa5a5a5a5&~0xff00)|0x8b00
 assert read(AFIO+4)==0x04001010 and read(RCC+0x1c)&0x00600000==0x00600000
 assert read(GPIOC+0xc)&(1<<11)
 assert read(CH3)&(1|2|8|32|128|8192)==(1|2|8|32|128|8192)
 assert read(CH3+4)==512 and read(CH3+8)==USART+4
 assert read(0xe000e100)&(1<<13) and u.mem_read(0xe000e400+13,1)==b'\x30'
 rx=t.call('stm3_uart_rx_buffer');assert read(CH3+12)==rx
 # Deliver100 bytes through circular DMA and read them in different chunk sizes.
 u.mem_write(rx,bytes(range(100)));write(CH3+4,412)
 assert t.call('stm3_uart_read',t.scratch,64)==64 and bytes(u.mem_read(t.scratch,64))==bytes(range(64))
 assert t.call('stm3_uart_read',t.scratch,64)==36 and bytes(u.mem_read(t.scratch,36))==bytes(range(64,100))
 # A pending TC flag is included before its IRQ, and is not counted twice afterward.
 u.mem_write(rx+100,bytes(i&255 for i in range(100,512)));write(CH3+4,512);write(DMA,1<<9)
 assert t.call('stm3_uart_read',t.scratch,512)==412
 assert bytes(u.mem_read(t.scratch,412))==bytes(i&255 for i in range(100,512))
 t.call('DMA1_Channel3_IRQHandler');assert read(DMA)&(1<<9)==0
 assert t.call('stm3_uart_read',t.scratch,64)==0
 # Continue after wrap, then deliberately overrun by more than one ring.
 u.mem_write(rx,bytes(i&255 for i in range(512,750)));write(CH3+4,274)
 assert t.call('stm3_uart_read',t.scratch,512)==238 and bytes(u.mem_read(t.scratch,238))==bytes(i&255 for i in range(512,750))
 write(DMA,1<<9);t.call('DMA1_Channel3_IRQHandler');write(CH3+4,224)
 assert t.call('stm3_uart_read',t.scratch,64)==0 and t.call('stm3_uart_errors')==1
 # Whole response packet is transmitted by DMA; its buffer stays pinned until done.
 tx=t.scratch+512;assert t.call('stm3_uart_tx_idle')==1
 u.mem_write(tx,b'T'*64);assert t.call('stm3_uart_tx_start',tx,64)==1
 assert read(CH2)&(1|16|128|4096)==(1|16|128|4096)
 assert read(CH2+4)==64 and read(CH2+8)==USART+4 and read(CH2+12)==tx
 assert t.call('stm3_uart_tx_idle')==0 and t.call('stm3_uart_tx_start',tx+64,1)==0
 write(CH2+4,0);write(DMA,1<<5)
 assert t.call('stm3_uart_tx_idle')==1
 write(USART,1<<1);t.call('stm3_uart_read',t.scratch,1);assert t.call('stm3_uart_errors')==2;write(USART,0)
 # DMA bus fault: invalidate partial input and re-arm the resident ring.
 write(DMA,1<<11);t.call('DMA1_Channel3_IRQHandler');assert not read(CH3)&1
 assert t.call('stm3_uart_errors')==3
 assert t.call('stm3_uart_read',t.scratch,64)==0 and read(CH3)&1 and read(CH3+4)==512
 t.call('stm3_uart_end');assert read(CH2)==0 and read(CH3)==0 and read(USART+0xc)==0
 assert read(GPIOC+4)==(0xa5a5a5a5&~0xff00)|0x4400
 assert t.call('stm3_uart_tx_idle')==0
 assert t.call('stm3_uart_begin',36000000)==1 and read(USART+8)==16
 report=dict(status='ARM_MMIO_MODEL_PASS',physical_io=False,physical_uart_rate_measured=False,pclk1_hz=36000000,brr=16,nominal_baud=2250000,format='8N1',rx_dma='DMA1 Channel3 circular512',tx_dma='DMA1 Channel2 direct caller packet272',tx_copy_bytes=0,wrong_clock_refused=True,busy_dma_refused=True,pmu_i2c_clock_bits_preserved=True,unrelated_gpio_bits_preserved=True,swj_power_gpio_setting_preserved=True,rx_pending_wrap_counted_once=True,rx_overrun_detected=True,rx_dma_fault_recovered=True,tx_buffer_lifetime_checked=True,uart_line_error_counted=True,per_byte_uart_interrupts=False,power_off_floats_uart=True,resume_reinitializes_dma=True)
 (B/'uart-dma-execution.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
