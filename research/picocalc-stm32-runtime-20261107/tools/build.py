#!/usr/bin/env python3
"""Compile only: produces STM32 keyboard/runtime firmware and native module."""
from pathlib import Path
import argparse,binascii,hashlib,json,shutil,struct,subprocess
from elf32 import ELF
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];B=ROOT/'.build/stm32-module-runtime-20261107'
TOOL=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/xpack-arm-none-eabi-gcc/14.2.1-1.1/bin')
def tool(name):return str(TOOL/('arm-none-eabi-'+name))
def run(cmd,log):
 with log.open('w')as out:subprocess.run(list(map(str,cmd)),check=True,stdout=out,stderr=subprocess.STDOUT)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def build_module():
 D=B/'module';D.mkdir(parents=True,exist_ok=True)
 flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g','-mword-relocations','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-fdata-sections','-ffunction-sections','-Wall','-Wextra','-Werror','-I'+str(R/'include')]
 elf=D/'q4_dot.elf';run([tool('gcc'),*flags,'-nostdlib',R/'modules/q4_dot.c','-Wl,-T,'+str(R/'modules/module.ld'),'-Wl,--emit-relocs,--gc-sections,-Map='+str(D/'q4_dot.map'),'-o',elf],D/'build.log')
 binary=D/'q4_dot.bin';subprocess.run([tool('objcopy'),'-O','binary','-j','.image',elf,binary],check=True)
 e=ELF(elf);image=binary.read_bytes();memory=e.symbols['__memory_end']['value']-0x20000000;bss=memory-len(image)
 relocs=[]
 for address,typ in e.relocations():
  if typ==2:relocs.append(address-0x20000000)
  elif typ not in [3,10,30,42]:raise ValueError('Unsupported ARM relocation '+str(typ))
 relocs=sorted(set(relocs));assert 0<len(relocs)<=64,'Demo must actually exercise relocation'
 for at in relocs:assert at%4==0 and at+4<=len(image) and 0x20000000<=struct.unpack_from('<I',image,at)[0]<=0x20000000+memory
 for name,s in e.symbols.items():assert s['index']!=0,'Undefined module symbol '+name
 payload=image+b''.join(struct.pack('<I',at)for at in relocs)
 words=[0x314d3353,1,64,64+len(payload),len(image),bss,e.entry-0x20000000,len(relocs),512,512,256,1000,binascii.crc32(payload),0,0x70301]
 header=struct.pack('<15I',*words);header+=struct.pack('<I',binascii.crc32(header))
 package=D/'q4_dot.s3m';package.write_bytes(header+payload)
 result=dict(file=str(package),sha256=sha(package),image_bytes=len(image),bss_bytes=bss,memory_bytes=memory,package_bytes=package.stat().st_size,relocations=relocs,entry_offset=e.entry-0x20000000,target='Cortex-M3 Thumb-2 soft ABI',physical_io=False)
 (D/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result

def build_harness():
 D=B/'arm-harness';D.mkdir(exist_ok=True)
 cmd=[tool('gcc'),'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g','-mword-relocations','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(R/'include'),'-I'+str(R/'runtime'),'-nostdlib',R/'runtime/stm3_runtime.c',R/'tests/arm_harness.c','-Wl,-T,'+str(R/'tests/harness.ld'),'-Wl,-Map='+str(D/'harness.map'),'-o',D/'harness.elf']
 run(cmd,D/'build.log');return D/'harness.elf'

def build_uart_harness():
 D=B/'uart-harness';D.mkdir(exist_ok=True)
 core=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/hardware/stm32/2.12.0')
 cmsis=Path('/Users/bolk/Library/Arduino15/packages/STMicroelectronics/tools/CMSIS/6.2.0/CMSIS/Core/Include')
 cmd=[tool('gcc'),'-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-DSTM32F103xB','-std=c11','-Os','-g','-ffreestanding','-fno-builtin','-I'+str(R/'firmware'),'-I'+str(cmsis),'-I'+str(core/'system/Drivers/CMSIS/Device/ST/STM32F1xx/Include'),'-nostdlib',R/'firmware/stm3_uart_dma.c',R/'tests/uart_harness.c','-Wl,-T,'+str(R/'tests/uart_harness.ld'),'-o',D/'uart.elf']
 run(cmd,D/'build.log');return D/'uart.elf'

def stage_sketch():
 D=B/'sketch/picocalc_keyboard';D.mkdir(parents=True,exist_ok=True)
 for f in(R/'vendor/picocalc_keyboard').iterdir():
  if f.is_file():shutil.copy2(f,D/f.name)
 for folder in ['include','runtime','firmware']:
  for f in(R/folder).iterdir():
   if f.suffix in ['.c','.cpp','.h']:shutil.copy2(f,D/f.name)
 p=D/'picocalc_keyboard.ino';text=p.read_text()
 # Keep all upstream power/I2C/key behavior; add UART servicing inside busy waits.
 text=text.replace('#include <Arduino.h>','#include <Arduino.h>\nextern "C" void coproc_setup();\nextern "C" void coproc_poll();',1)
 old='while ( (millis() - last_tick) < n);';assert text.count(old)==1
 text=text.replace(old,'while ( (millis() - last_tick) < (unsigned)n) { coproc_poll(); }')
 old='  //printf("Start pico");';assert text.count(old)==1
 text=text.replace(old,'  coproc_setup();\n'+old)
 # Skip UART work until setup completed: upstream also uses nbDelay during boot.
 text=text.replace('extern "C" void coproc_poll();','extern "C" void coproc_poll();')
 p.write_text(text);return D

def build_firmware():
 sketch=stage_sketch();D=B/'firmware';D.mkdir(exist_ok=True)
 cmd=['arduino-cli','--config-file',B/'arduino.yaml','compile','-b','STMicroelectronics:stm32:GenF1:pnum=GENERIC_F103R8TX,xserial=generic,usb=none,opt=oslto','--library',B/'XPowersLib','--build-path',B/'firmware-build','--output-dir',D,'--jobs','4',sketch]
 run(cmd,B/'firmware-build.log')
 e=D/'picocalc_keyboard.ino.elf';elf=ELF(e)
 size=subprocess.check_output([tool('size'),str(e)],text=True);print(size.strip())
 text,data,bss=map(int,size.splitlines()[-1].split()[:3]);assert text+data<=65536 and data+bss+4096<=20480,'Need4KiB headroom for heap/stack'
 result=dict(elf=str(e),bin=str(D/'picocalc_keyboard.ino.bin'),elf_sha256=sha(e),bin_sha256=sha(D/'picocalc_keyboard.ino.bin'),flash_bytes=text+data,ram_linked_bytes_including_heap_stack_reserve=data+bss,ram_remaining_bytes=20480-data-bss,ram_budget=20480,flash_budget=65536,physical_io=False,deployed=False,uart=dict(instance='USART3',rx='PC11',tx='PC10',baud=2250000,flow='COBS+CRC32 stop-and-wait',rx_dma='DMA1 Channel3 circular512B',tx_dma='DMA1 Channel2 normal272B',format='8N1',ideal_bytes_per_second_per_direction=225000,hardware_rate_measured=False))
 result['runtime_bytes']=elf.symbols.get('_ZL6coproc',{}).get('size')
 (D/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--firmware',action='store_true');a=ap.parse_args();B.mkdir(parents=True,exist_ok=True)
 result=dict(module=build_module(),arm_harness=str(build_harness()),uart_harness=str(build_uart_harness()))
 if a.firmware:result['firmware']=build_firmware()
 (B/'build-summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
