#!/usr/bin/env python3
"""Stage a pinned Southbridge port and compile it. Never opens a device."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
P=Path(__file__).resolve().parent;R=P.parent;ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107';B=BASE/'southbridge-runtime'
S=BASE/'community-southbridge';D=B/'source'
sys.path.insert(0,str(R/'tools'))
from elf32 import ELF
from build import TOOL,tool,run
from i2c_fix import patch_callbacks,patch_main,patch_header
PINS={'.':'1b649c826b213b460bca7172f696ec7619d93be0',
      'Drivers/CMSIS':'f37cfcee997e714b0fad374a328c41df64f99acb',
      'Drivers/CMSIS_Device_ST_STM32F1xx':'c8e9a4a4f16b6d2cb2a2083cbe5161025280fb22',
      'Drivers/STM32F1xx_HAL_Driver':'06d3b0c169557f49aa14c14d8ed4d920bbd3078e'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def replace(text,old,new):
 assert text.count(old)==1,(old,text.count(old));return text.replace(old,new,1)
def remove_function(text,signature):
 start=text.index(signature);at=text.index('{',start);depth=1;end=at+1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[:start]+text[end:]
def stage(i2c_expiry_fix=False,power_status=False):
 for path,commit in PINS.items():
  actual=subprocess.check_output(['git','-C',str(S/path),'rev-parse','HEAD'],text=True).strip()
  assert actual==commit,(path,actual)
  assert not subprocess.check_output(['git','-C',str(S/path),'diff','--name-only','HEAD'],text=True).strip(),path
 D.mkdir(parents=True,exist_ok=True)
 shutil.copytree(S/'Core',D/'Core',dirs_exist_ok=True)
 for name in ['Makefile','STM32F103XX_FLASH.ld','startup_stm32f103xb.s','LICENSE']:
  if(S/name).exists():shutil.copy2(S/name,D/name)
 if not(D/'Drivers').exists():(D/'Drivers').symlink_to(S/'Drivers',target_is_directory=True)
 src=D/'Core/Src';inc=D/'Core/Inc'
 for folder in ['runtime','firmware']:
  for p in(P/folder).iterdir():
   if p.suffix in ['.c','.h']:shutil.copy2(p,(src if p.suffix=='.c'else inc)/p.name)
 shutil.copy2(R/'include/stm3_module.h',inc/'stm3_module.h')
 # Upstream step-based brightness is replaced by stock-compatible byte values.
 (src/'backlight.c').write_text((P/'firmware/backlight_compat.c').read_text())
 (src/'backlight_compat.c').unlink()
 h=(inc/'hal_interface.h').read_text()
 h=replace(h,'#define HAL_INTERFACE_H_','#define HAL_INTERFACE_H_\n#include "coproc_hal.h"')
 h=replace(h,'__STATIC_INLINE void sys_stop_pico(void) {','__STATIC_INLINE void sys_stop_pico(void) {\n\tcoproc_suspend();')
 h=replace(h,'LL_GPIO_SetOutputPin(SP_AMP_EN_GPIO_Port, SP_AMP_EN_Pin);\t// Enable speaker Amp. power',
           'LL_GPIO_SetOutputPin(SP_AMP_EN_GPIO_Port, SP_AMP_EN_Pin);\t// Enable speaker Amp. power\n\tcoproc_resume();')
 (inc/'hal_interface.h').write_text(h)
 h=(src/'hal_interface.c').read_text()
 h=remove_function(h,'void SystemClock_Config(void)')
 h=h.replace('#ifdef UART_PICO_INTERFACE','#if defined(UART_PICO_INTERFACE) && !defined(STM3_MODULE_RUNTIME)')
 h=replace(h,'htim1.Init.Prescaler = 0;','htim1.Init.Prescaler = 18-1;')
 h=replace(h,'htim3.Init.Prescaler = 0;','htim3.Init.Prescaler = 18-1;')
 h=replace(h,'htim2.Init.Prescaler = 4-1;','htim2.Init.Prescaler = 72-1;')
 h=replace(h,'htim2.Init.Period = 1000;','htim2.Init.Period = 1000-1;')
 h=replace(h,'\tFLASH_OBProgramInitTypeDef flash_s;','')
 start=h.index('\t// Check options registers values');end=h.index('\n\treturn result;',start)
 h=h[:start]+'\t// Option bytes are never programmed by this port.\n'+h[end:]
 (src/'hal_interface.c').write_text(h)
 it=(src/'stm32f1xx_it.c').read_text().replace('#ifdef UART_PICO_INTERFACE','#if defined(UART_PICO_INTERFACE) && !defined(STM3_MODULE_RUNTIME)')
 (src/'stm32f1xx_it.c').write_text(it)
 i2c=(src/'i2cs.c').read_text()
 line='\t\t\t\t\tLL_GPIO_SetOutputPin(PICO_IRQ_GPIO_Port, PICO_IRQ_Pin);\t// De-assert the IRQ signal'
 i2c=replace(i2c,line,'#ifndef UART_PICO_INTERFACE\n'+line+'\n#endif')
 (src/'i2cs.c').write_text(i2c)
 main=(src/'main.c').read_text()
 main=replace(main,'#define DEFAULT_LCD_BL\t\t(3)\t\t//step-4 (~50%)','#define DEFAULT_LCD_BL\t\t(32)\t\t// stock raw brightness')
 main=replace(main,'if ((uint16_t)result != 0xCA1C)','if ((uint16_t)result != 0xCA3C)')
 main=replace(main,'EEPROM_VAR_ID, (EEPROM_Value)(uint16_t)0xCA1C','EEPROM_VAR_ID, (EEPROM_Value)(uint16_t)0xCA3C')
 main=replace(main,'\t// PICO MCU start','\tcoproc_setup();\n\t// PICO MCU start')
 main=replace(main,'\t\treg_sync();','\t\tif (coproc_storage_idle()) reg_sync();')
 main=replace(main,'\t\tkeyboard_process();\n\t\thw_check_HP_presence();','\t\tkeyboard_process();\n\t\tcoproc_poll();\n\t\thw_check_HP_presence();')
 start=main.index('\t\t\t\tHAL_SuspendTick();');end=main.index('\n\t\t\t\tHAL_Delay(300);',start)
 main=main[:start]+'\t\t\t\tcoproc_enter_sleep();'+main[end:]
 if i2c_expiry_fix:
  (src/'i2cs.c').write_text(patch_callbacks((src/'i2cs.c').read_text()))
  (inc/'i2cs.h').write_text(patch_header((inc/'i2cs.h').read_text()))
  main=patch_main(main)
 (src/'main.c').write_text(main)
 regs=(src/'regs.c').read_text()
 regs=replace(regs,'(uint8_t)((buff >> 8) & 0xFF) % LCD_BCKL_STEPS','(uint8_t)((buff >> 8) & 0xFF)')
 regs=replace(regs,'(uint8_t)(buff & 0xFF) % KBD_BCKL_STEPS','(uint8_t)(buff & 0xFF)')
 (src/'regs.c').write_text(regs)
 ld=(D/'STM32F103XX_FLASH.ld').read_text()
 ld=replace(ld,'_Min_Heap_Size = 0x200;','_Min_Heap_Size = 0;')
 ld=replace(ld,'_Min_Stack_Size = 0x400;','_Min_Stack_Size = 0x1000;')
 ld+='\n_sstack = _estack - _Min_Stack_Size;\nASSERT(_ebss + 2048 <= _sstack, "Need 2KiB unallocated safety gap below 4KiB stack")\n'
 # Use the compiler's freestanding memory routines; no allocation/syscall ABI.
 ld=ld.replace('    libc.a ( * )','').replace('    libgcc.a ( * )','')
 (D/'STM32F103XX_FLASH.ld').write_text(ld)
 make=(D/'Makefile').read_text()
 extra=['stm3_runtime','stm3_uart_dma','coproc_hal','clock72']
 make=replace(make,'Core/Src/main.c \\','Core/Src/main.c \\\n'+''.join('Core/Src/'+n+'.c \\\n'for n in extra).rstrip('\n'))
 make=replace(make,'-DSTM32F103xB','-DSTM32F103xB -DUART_PICO_INTERFACE -DSTM3_MODULE_RUNTIME')
 make=replace(make,'-fdata-sections -ffunction-sections --specs=$(SPECS)\n\nifeq','-fdata-sections -ffunction-sections -fstack-usage --specs=$(SPECS)\n\nifeq')
 make=replace(make,'-Wl,--gc-sections -static','-Wl,--gc-sections,--undefined=coproc_stack_unused -flto -fstack-usage -static')
 (D/'Makefile').write_text(make)
 if power_status:
  sys.path.insert(0,str(ROOT/'tools/firmware/picocalc'))
  from bios_power import stage_power_status
  stage_power_status(D)
 files={str(f.relative_to(D)):sha(f)for f in D.rglob('*')if f.is_file()and not f.is_relative_to(D/'Drivers')and not f.is_relative_to(D/'build')}
 (B/'staged-sources.json').write_text(json.dumps(dict(upstream=PINS,files=files),indent=2)+'\n')
 return D
def build(i2c_expiry_fix=False,power_status=False):
 stage(i2c_expiry_fix,power_status);out=D/'build'
 run(['make','-C',D,'-j4','GCC_PATH='+str(TOOL),'OPT=-Os -flto','BUILD_DIR=build'],B/'firmware-build.log')
 e=out/'picocalc_BIOS_jcs.elf';binary=out/'picocalc_BIOS_jcs.bin';elf=ELF(e)
 globals=(elf.symbols['_edata']['value']-elf.symbols['_sdata']['value']+
          elf.symbols['_ebss']['value']-elf.symbols['_sbss']['value'])
 stack=4096;gap=20480-globals-stack
 assert binary.stat().st_size<=62*1024 and gap>=2048
 assert elf.symbols['_sstack']['value']==0x20004000
 assert not any(n in elf.symbols for n in ['module_entry','malloc','calloc','realloc','free','_sbrk','HAL_FLASHEx_OBProgram','HAL_FLASH_OB_Launch'])
 result=dict(status='COMPILED',elf=str(e),bin=str(binary),elf_sha256=sha(e),bin_sha256=sha(binary),
             flash_image_bytes=binary.stat().st_size,flash_settings_reserved_bytes=2048,
             flash_unused_bytes=65536-2048-binary.stat().st_size,
             global_ram_bytes=globals,stack_reserved_bytes=stack,heap_reserved_bytes=0,
             ram_unallocated_bytes=gap,ram_budget_bytes=20480,
             runtime_bytes=elf.symbols['coproc']['size'],module_code_bss_limit_bytes=6144,
             clock_hz=72000000,apb1_hz=36000000,uart_baud=2250000,uart_format='8N1',
             rx_dma_bytes=512,tx_dma_copy_bytes=0,option_byte_programming=False,
             physical_io=False,deployed=False,hardware_timing_tested=False)
 result['i2c_expiry_fix']=i2c_expiry_fix
 if power_status:result['power_status_protocol']=1
 result['staged_sources_sha256']=sha(B/'staged-sources.json')
 (B/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output-dir',type=Path,help='Separate repository build directory')
 parser.add_argument('--i2c-expiry-fix',action='store_true')
 parser.add_argument('--power-status',action='store_true',help='Add MK61 read-only AXP2101 power status ABI1')
 args=parser.parse_args()
 if args.output_dir:
  candidate=args.output_dir.resolve()
  if not candidate.is_relative_to(ROOT) or candidate in (ROOT,BASE):
   parser.error('--output-dir must be a separate subdirectory of the repository')
  B=candidate;D=B/'source'
 if (args.i2c_expiry_fix or args.power_status) and B==BASE/'southbridge-runtime':
  parser.error('BIOS extensions require a separate --output-dir; installed sources stay pinned')
 build(args.i2c_expiry_fix,args.power_status)
