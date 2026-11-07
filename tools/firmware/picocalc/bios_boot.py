"""Stage the resident half of the M3 updater; no device I/O."""
from pathlib import Path
import re
import shutil
ROOT=Path(__file__).resolve().parents[3]

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('M3 boot source anchor changed: '+old)
    return text.replace(old,new,1)

def stage(source):
    source=Path(source);inc=source/'Core/Inc';src=source/'Core/Src'
    runtime=(src/'stm3_runtime.c').read_text()
    runtime=once(runtime,'#include "stm3_runtime.h"','#include "stm3_runtime.h"\n#include "m3b_entry.h"\n#include "protocol.h"')
    runtime=once(runtime,'case STM3_HELLO:', '''case M3B_ENTER:
  if(n!=8 || get32(in)!=M3B_ENTER_MAGIC || get32(in+4)!=M3B_TARGET){error=STM3_E_ARGUMENT;break;}
  if(r->state!=STM3_EMPTY){error=STM3_E_STATE;break;}
  bios_update_requested=1;break;
 case STM3_HELLO:''')
    runtime,count=re.subn(r'put32\(out\+36,([^;]+)\);',r'put32(out+36,(\1)|16u);',runtime)
    if count!=1:raise ValueError('M3 HELLO flags anchor changed')
    coproc=(src/'coproc_hal.c').read_text()
    coproc=once(coproc,'#include "coproc_hal.h"','#include "coproc_hal.h"\n#include "m3b_entry.h"')
    coproc=once(coproc,'void coproc_poll(void){\n if(!ready)return;',
      'void coproc_poll(void){\n if(!ready)return;\n if(bios_update_requested && coproc.tx_at==coproc.tx_bytes && stm3_uart_tx_idle())bios_boot_enter();')
    hal=(src/'hal_interface.c').read_text()
    hal=once(hal,'#include "hal_interface.h"','#include "hal_interface.h"\n#include "m3b_entry.h"')
    hal=once(hal,'LL_GPIO_ResetOutputPin(GPIOA, PICO_EN_Pin|SP_AMP_EN_Pin);',
      'if(bios_boot_keep_pico()){LL_GPIO_SetOutputPin(GPIOA,PICO_EN_Pin);LL_GPIO_ResetOutputPin(GPIOA,SP_AMP_EN_Pin);}\n\telse LL_GPIO_ResetOutputPin(GPIOA, PICO_EN_Pin|SP_AMP_EN_Pin);')
    system=(src/'system_stm32f1xx.c').read_text()
    system=once(system,'/* #define USER_VECT_TAB_ADDRESS */','#define USER_VECT_TAB_ADDRESS')
    system=once(system,'#define VECT_TAB_BASE_ADDRESS   FLASH_BASE', '#define VECT_TAB_BASE_ADDRESS   (FLASH_BASE + 0x2000U)')
    ld=(source/'STM32F103XX_FLASH.ld').read_text()
    ld=once(ld,'ORIGIN = 0x20000000, LENGTH = 20K','ORIGIN = 0x20000000, LENGTH = 20K-32')
    ld=once(ld,'ORIGIN = 0x8000000, LENGTH = 62K','ORIGIN = 0x8002000, LENGTH = 53K')
    make=(source/'Makefile').read_text()
    make=once(make,'Core/Src/main.c \\', 'Core/Src/main.c \\\nCore/Src/m3b_entry.c \\')
    # Validate every source anchor before writing any staged source.
    for path,text in [(src/'stm3_runtime.c',runtime),(src/'coproc_hal.c',coproc),
                      (src/'hal_interface.c',hal),(src/'system_stm32f1xx.c',system),
                      (source/'STM32F103XX_FLASH.ld',ld),(source/'Makefile',make)]:path.write_text(text)
    boot=ROOT/'ports/picocalc/bios/boot'
    for original,target in [('entry.c',src/'m3b_entry.c'),('entry.h',inc/'m3b_entry.h'),('protocol.h',inc/'protocol.h')]:shutil.copyfile(boot/original,target)
