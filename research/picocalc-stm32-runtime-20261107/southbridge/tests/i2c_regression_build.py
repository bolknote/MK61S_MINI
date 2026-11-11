"""Build exact installed and fixed I2C callbacks with a peripheral-only fixture."""
from pathlib import Path
import difflib
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
P=Path(__file__).resolve().parents[1];R=P.parent;ROOT=R.parents[1]
B=ROOT/'.build/mk61ai/i2c-expiry-fix'
INSTALLED=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime/source'
sys.path[:0]=[str(R/'tools'),str(P)]
from i2c_fix import patch_callbacks,patch_main,patch_header
from build import tool

EXTRA=r'''
static uint32_t forced_api_status,side_effects,race_write;
HAL_I2C_StateTypeDef HAL_I2C_GetState(I2C_HandleTypeDef*h){return h->State;}
uint32_t led_blink_configure(uint8_t count,uint8_t restore){(void)count;(void)restore;return 0;}
void HAL_Interface_I2C1_reset(void){
 hi2c1.State=HAL_I2C_STATE_LISTEN;I2C1->CR1=I2C_CR1_PE;I2C1->SR1=0;
 if(race_write){race_write=0;HAL_I2C_AddrCallback(&hi2c1,I2C_DIRECTION_TRANSMIT,0x3e);}
}
__attribute__((used)) uint32_t harness_address(uint32_t direction){
 tx_n=0;rx_n=0;I2C1->SR1|=I2C_SR1_ADDR;
 HAL_I2C_AddrCallback(&hi2c1,(uint8_t)direction,0x3e);
 return ((I2C1->CR1&I2C_CR1_PE)&&(I2C1->SR1&I2C_SR1_ADDR))?1:0;
}
__attribute__((used)) uint32_t harness_rx_byte(uint32_t byte){
 if(!rx_at||rx_n!=1)return 0;
 *rx_at=(uint8_t)byte;rx_n=0;HAL_I2C_SlaveRxCpltCallback(&hi2c1);return 1;
}
__attribute__((used)) uint32_t harness_rx_payload(uint32_t value,uint32_t n){
 if(!rx_at||n!=rx_n||n>4)return 0;
 for(uint32_t i=0;i<n;++i)rx_at[i]=(uint8_t)(value>>(8*i));
 rx_n=0;HAL_I2C_SlaveRxCpltCallback(&hi2c1);return 1;
}
__attribute__((used)) uint32_t harness_stop(void){HAL_I2C_ListenCpltCallback(&hi2c1);return i2cs_state;}
__attribute__((used)) uint32_t harness_tx_word(void){return tx_n==2?((uint32_t)tx_bytes[0]<<8)|tx_bytes[1]:0xffffffffu;}
__attribute__((used)) uint32_t harness_tx_size(void){return tx_n;}
__attribute__((used)) uint32_t harness_state(void){return i2cs_state;}
__attribute__((used)) uint32_t harness_effects(void){return side_effects;}
__attribute__((used)) uint32_t harness_force_api(uint32_t status){forced_api_status=status;return status;}
__attribute__((used)) uint32_t harness_race_write(void){race_write=1;return 1;}
__attribute__((used)) uint32_t harness_enabled(void){return I2C1->CR1&I2C_CR1_PE;}
__attribute__((used)) uint32_t harness_held(void){return ((I2C1->CR1&I2C_CR1_PE)&&(I2C1->SR1&I2C_SR1_ADDR))?1:0;}
__attribute__((used)) uint32_t harness_watchdog(uint32_t now){
 systicks_counter=now;
 __WATCHDOG__
 return i2cs_state;
}
'''
POWER_EXTRA=r'''
#include "power_status.h"
static uint32_t pmu_raw,pmu_status;
uint8_t*reg_raw_access(void){return regs;}
HAL_StatusTypeDef HAL_I2C_Mem_Read(I2C_HandleTypeDef*h,uint16_t dev,uint16_t reg,uint16_t width,uint8_t*p,uint16_t n,uint32_t timeout){
 if(h!=&hi2c2||dev!=0x68||reg||width!=I2C_MEMADD_SIZE_8BIT||n!=2||timeout!=4)__builtin_trap();
 p[0]=(uint8_t)pmu_raw;p[1]=(uint8_t)(pmu_raw>>8);return (HAL_StatusTypeDef)pmu_status;
}
__attribute__((used)) uint32_t harness_power(uint32_t raw,uint32_t status,uint32_t online){
 pmu_raw=raw;pmu_status=status;bios_power_refresh((uint8_t)online);
 return regs[BIOS_POWER_REG]|((uint32_t)regs[REG_ID_BAT]<<8);
}
'''

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--fixed-source',type=Path)
 candidate=parser.parse_args().fixed_source
 if candidate:candidate=candidate.resolve()
 B.mkdir(parents=True,exist_ok=True)
 frozen=B/'installed-source'
 if not frozen.exists():shutil.copytree(INSTALLED/'Core',frozen/'Core')
 original=(frozen/'Core/Src/i2cs.c').read_text();main_source=(frozen/'Core/Src/main.c').read_text()
 base=(P/'tests/combined_harness.c').read_text()
 base=base.replace('static uint8_t regs[REG_ID_LAST],tx_bytes[10],tx_n;','static uint32_t forced_api_status,side_effects,race_write;\nstatic uint8_t regs[REG_ID_LAST],tx_bytes[10],tx_n;')
 base=base.replace('regs[r]=v;}','regs[r]=v;++side_effects;}')
 base=base.replace('(void)h;(void)d;(void)f;return HAL_OK;',
                   '(void)h;(void)d;(void)f;++side_effects;return HAL_OK;')
 for kind in ('date','time'):
  old='void i2cs_RTC_'+kind+'_from_buffer(volatile RTC_'+kind.title()+'TypeDef*const p,const uint8_t*const b){(void)b;(void)p;}'
  assert old in base,old
  base=base.replace(old,old[:-1]+'++side_effects;}')
 base=base.replace('(void)h;(void)flags;rx_at=p;rx_n=n;return HAL_OK;',
                   '(void)flags;if(forced_api_status)return (HAL_StatusTypeDef)forced_api_status;if(!n)return HAL_ERROR;h->Instance->SR1&=~I2C_SR1_ADDR;rx_at=p;rx_n=n;return HAL_OK;')
 base=base.replace('(void)h;(void)flags;if(n>10)',
                   '(void)flags;if(forced_api_status)return (HAL_StatusTypeDef)forced_api_status;h->Instance->SR1&=~I2C_SR1_ADDR;if(n>10)')
 base=base.replace('HAL_I2C_EnableListen_IT(I2C_HandleTypeDef*h){(void)h;return HAL_OK;}',
                   'HAL_I2C_EnableListen_IT(I2C_HandleTypeDef*h){h->State=HAL_I2C_STATE_LISTEN;return HAL_OK;}')
 base=base.replace('htim1.Instance=TIM1;', 'hi2c1.Instance=I2C1;hi2c1.State=HAL_I2C_STATE_LISTEN;I2C1->CR1=I2C_CR1_PE;\n htim1.Instance=TIM1;')
 # Globals are declared before the callbacks that use them.
 extra=EXTRA.replace('static uint32_t forced_api_status,side_effects,race_write;\n','')
 reports=[]
 for fixed in [False,True]:
  out=B/('fixed'if fixed else'original');inc=out/'inc';inc.mkdir(parents=True,exist_ok=True)
  core=candidate/'Core'if fixed and candidate else frozen/'Core'
  for p in(core/'Inc').glob('*'):shutil.copy2(p,inc/p.name)
  if fixed and not candidate:
   h=inc/'i2cs.h';h.write_text(patch_header(h.read_text()))
  shutil.copy2(P/'firmware/i2cs_recovery.h',inc/'i2cs_recovery.h')
  callbacks=patch_callbacks(original)if fixed else original
  main=patch_main(main_source)if fixed else main_source
  power=fixed and candidate and (inc/'power_status.h').exists()
  if fixed and candidate:
   actual=(core/'Src/i2cs.c').read_text()
   if power:
    power_branch='} else if (reg == REG_ID_POWER_STATUS) {\n\t\t\t\t\ti2cs_w_buff[1] = reg_get_value(REG_ID_POWER_STATUS);\n\t\t\t\t} else if (reg == REG_ID_BAT) {'
    assert actual.count(power_branch)==1
    assert actual.replace(power_branch,'} else if (reg == REG_ID_BAT) {')==callbacks
   else:assert actual==callbacks
   callbacks=actual
   assert (inc/'i2cs.h').read_text()==patch_header((frozen/'Core/Inc/i2cs.h').read_text())
   main=(core/'Src/main.c').read_text()
  (out/'i2cs.c').write_text(callbacks)
  start=main.index('\t\tif (',main.index('// Re-arm I2CS'))
  end=main.index('\n\n\t\tif (coproc_storage_idle())',start)
  watchdog=main[start:end]
  expected_main=patch_main(main_source)if fixed else main_source
  expected_start=expected_main.index('\t\tif (',expected_main.index('// Re-arm I2CS'))
  expected_end=expected_main.index('\n\n\t\tif (coproc_storage_idle())',expected_start)
  assert watchdog==expected_main[expected_start:expected_end]
  harness=base+extra.replace('__WATCHDOG__',watchdog)+(POWER_EXTRA if power else'')
  if fixed:harness='#include "i2cs_recovery.h"\n'+harness
  (out/'harness.c').write_text(harness)
  drivers=INSTALLED/'Drivers'
  flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=gnu17','-Os','-g','-ffreestanding','-fno-builtin',
   '-fdata-sections','-ffunction-sections','-DSTM32F103xB','-DUSE_HAL_DRIVER','-DUSE_FULL_LL_DRIVER',
   '-DUART_PICO_INTERFACE','-DSTM3_MODULE_RUNTIME','-I'+str(inc),'-I'+str(drivers/'STM32F1xx_HAL_Driver/Inc'),
   '-I'+str(drivers/'CMSIS_Device_ST_STM32F1xx/Include'),'-I'+str(drivers/'CMSIS/Include')]
  sources=[core/'Src'/(n+'.c')for n in ['stm3_runtime','stm3_uart_dma','coproc_hal','clock72','fifo','backlight']]
  if power:sources.append(core/'Src/power_status.c')
  sources += [out/'i2cs.c',out/'harness.c',drivers/'STM32F1xx_HAL_Driver/Src/stm32f1xx_ll_utils.c']
  target=out/'combined-harness/combined.elf';target.parent.mkdir(exist_ok=True)
  command=[tool('gcc'),*flags,'-nostdlib',*map(str,sources),'-lgcc','-Wl,--gc-sections,-T,'+str(P/'tests/combined.ld'),'-o',str(target)]
  with(out/'build.log').open('w')as log:subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
  reports.append(dict(variant=out.name,elf=str(target),sha256=hashlib.sha256(target.read_bytes()).hexdigest(),power_status=bool(power),
   fixed_source=str(candidate)if fixed and candidate else None))
 (B/'callbacks.patch').write_text(''.join(difflib.unified_diff(original.splitlines(True),patch_callbacks(original).splitlines(True),fromfile='installed/i2cs.c',tofile='fixed/i2cs.c')))
 (B/'build.json').write_text(json.dumps(dict(status='HOST_COMPILED_NOT_DEPLOYED',physical_io=False,
   installed_callbacks_sha256=hashlib.sha256(original.encode()).hexdigest(),variants=reports),indent=2)+'\n')
 print(json.dumps(reports,indent=2))
if __name__=='__main__':main()
