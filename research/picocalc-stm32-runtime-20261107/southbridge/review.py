#!/usr/bin/env python3
"""Check source/artifact gates and emit a review packet; no hardware actions."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,struct,sys
P=Path(__file__).resolve().parent;R=P.parent;ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107';B=BASE/'southbridge-runtime'
S=BASE/'community-southbridge';D=B/'source'
sys.path.insert(0,str(R/'tools'))
from elf32 import ELF
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 m=json.loads((B/'manifest.json').read_text());image=Path(m['bin']);elf=ELF(m['elf'])
 assert sha(image)==m['bin_sha256']and sha(Path(m['elf']))==m['elf_sha256']
 staged=json.loads((B/'staged-sources.json').read_text())
 for name,digest in staged['files'].items():assert sha(D/name)==digest,name
 changed=[]
 for p in(S/'Core').rglob('*'):
  if p.is_file()and p.read_bytes()!=(D/p.relative_to(S)).read_bytes():changed.append(str(p.relative_to(S)))
 expected=['Core/Inc/hal_interface.h','Core/Src/backlight.c','Core/Src/hal_interface.c',
           'Core/Src/i2cs.c','Core/Src/main.c','Core/Src/regs.c','Core/Src/stm32f1xx_it.c']
 if m.get('i2c_expiry_fix'):expected.append('Core/Inc/i2cs.h')
 if m.get('power_status_protocol'):expected.append('Core/Inc/regs.h')
 assert sorted(changed)==sorted(expected),changed
 for folder in ['runtime','firmware']:
  for p in(P/folder).iterdir():
   if p.suffix not in ['.c','.h']:continue
   target=D/('Core/Inc'if p.suffix=='.h'else'Core/Src')/p.name
   if p.name=='backlight_compat.c':target=D/'Core/Src/backlight.c'
   assert p.read_bytes()==target.read_bytes(),p
 assert sha(R/'include/stm3_module.h')==sha(D/'Core/Inc/stm3_module.h')
 sp,reset=struct.unpack_from('<II',image.read_bytes());assert sp==0x20005000 and reset&1
 assert 0x08000000<=reset<0x0800f800
 dma_vector=struct.unpack_from('<I',image.read_bytes(),4*(16+13))[0]
 assert dma_vector==elf.symbols['DMA1_Channel3_IRQHandler']['value']
 assert 'module_entry'not in elf.symbols
 for name in ['malloc','calloc','realloc','free','_sbrk','HAL_FLASHEx_OBProgram','HAL_FLASH_OB_Launch']:
  assert name not in elf.symbols,name
 hal=(D/'Core/Src/hal_interface.c').read_text()
 for text in ['htim1.Init.Prescaler = 18-1;','htim3.Init.Prescaler = 18-1;',
              'htim2.Init.Prescaler = 72-1;','htim2.Init.Period = 1000-1;']:assert text in hal
 header=(D/'Core/Inc/hal_interface.h').read_text()
 off=header.split('__STATIC_INLINE void sys_stop_pico(void) {')[1].split('}')[0]
 on=header.split('__STATIC_INLINE void sys_start_pico(void) {')[1].split('}')[0]
 assert off.index('coproc_suspend()')<off.index('LL_GPIO_ResetOutputPin')
 assert on.index('coproc_resume()')>on.index('LL_GPIO_SetOutputPin(SP_AMP_EN')
 main_src=(D/'Core/Src/main.c').read_text()
 assert 'if (coproc_storage_idle()) reg_sync();'in main_src
 assert 'EEPROM_VAR_ID, (EEPROM_Value)(uint16_t)0xCA3C'in main_src
 assert 'HAL_RTCEx_BKUPWrite(&hrtc, RTC_BKP_DR1, 0xCA1C)'in main_src
 make=(D/'Makefile').read_text();assert not any(x in make for x in ['ports/picocalc','code/mk61','q4_dot.c'])
 reports={name:json.loads((B/(name+'.json')).read_text())for name in ['host-verification','arm-execution','uart-dma-execution','combined-execution']}
 regression_path=None
 if m.get('i2c_expiry_fix'):
  regression_path=ROOT/'.build/mk61ai/i2c-expiry-fix/regression.json'
  reports['i2c-expiry-regression']=json.loads(regression_path.read_text())
  assert (D/'Core/Src/i2cs.c').read_bytes()==(regression_path.parent/'fixed/i2cs.c').read_bytes()
  assert (D/'Core/Inc/i2cs.h').read_bytes()==(regression_path.parent/'fixed/inc/i2cs.h').read_bytes()
 power_report=None
 power_inputs=[]
 if m.get('power_status_protocol'):
  power_report=B/'power-status-host.json'
  reports['power-status-host']=json.loads(power_report.read_text())
  for name in ('power_status.c','power_status.h'):
   source=ROOT/'ports/picocalc/bios'/name
   assert sha(source)==sha(D/('Core/Src'if name.endswith('.c')else'Core/Inc')/name)
   power_inputs.append(source)
  power_inputs += [ROOT/'tools/firmware/picocalc/bios_power.py',ROOT/'tests/picocalc_bios_power_self_test.py',
                   ROOT/'tests/picocalc_bios_power_self_test.c']
  power_inputs+=sorted((ROOT/'tests/fixtures/picocalc_bios_power_hal').glob('*.h'))
 for name,report in reports.items():assert 'PASS'in report['status']and report['physical_io']is False,name
 assert reports['arm-execution']['rows_checked']==309
 assert reports['combined-execution']['q4_dot_rows']==72
 assert reports['uart-dma-execution']['rx_dma_fault_recovered']is True
 assert m['global_ram_bytes']+m['stack_reserved_bytes']+m['ram_unallocated_bytes']==20480
 assert m['ram_unallocated_bytes']>=2048 and m['flash_image_bytes']<=62*1024
 package=B/'module/q4_dot.s3m';assert sha(package)=='b41523b6bb827859697ce754511938ac985d070cff7c76d3666ac32ed9c2dae7'
 static_frames=[]
 for p in(D/'build').glob('*.su'):
  for line in p.read_text().splitlines():
   fields=line.split('\t')
   if len(fields)==3:static_frames.append(dict(function=fields[0],bytes=int(fields[1]),kind=fields[2]))
 assert static_frames,'Compiler stack-use report must exist'
 pages=(image.stat().st_size+1023)//1024;assert pages<=62
 plan=dict(executed=False,port_requires_fresh_identification='/dev/cu.usbserial-1120',
           physical_boot_step='DIP1 ON, board power cycle; query ROM chip ID before writing',
           expected_rom_chip_id='0x410 STM32F1 medium density; confirm board R8/64KiB geometry',
           info_argv=[str(BASE/'stm32flash/stm32flash'),'-b','57600','-m','8e1','/dev/cu.usbserial-1120'],
           write_verify_argv=[str(BASE/'stm32flash/stm32flash'),'-b','57600','-m','8e1','-n','0','-f','-w',str(image),'-v',
                              '-s','0','-e',str(pages),'/dev/cu.usbserial-1120'],
           start_address='0x08000000',erase_pages=pages,page_size=1024,
           erased_end_exclusive=hex(0x08000000+pages*1024),settings_range_untouched_by_programmer='0x0800f800..0x08010000',
           automatic_go_or_reset=False,option_bytes_or_protection_changes=False,
           old_firmware_or_calculator_state_backup=False,
           after_write='DIP1 OFF and board power cycle; validate keyboard/power before module jobs')
 (B/'flash-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 files=[Path(m['elf']),image,D/'build/picocalc_BIOS_jcs.hex',package,
        B/'manifest.json',B/'staged-sources.json',B/'flash-plan.json',
        *[B/(name+'.json')for name in reports if name!='i2c-expiry-regression'],B/'arm-harness/harness.elf',
        B/'uart-harness/uart.elf',B/'combined-harness/combined.elf']
 files+=sorted(p for p in P.rglob('*')if p.is_file()and '__pycache__'not in p.parts)
 if regression_path:
  files+=[regression_path,regression_path.parent/'build.json',regression_path.parent/'callbacks.patch']
 files+=power_inputs
 packet=dict(status='SOUTHBRIDGE_COMPILED_HOST_ARM_TESTED_NOT_FLASHED',created_utc=datetime.now(timezone.utc).isoformat(),
             physical_io=False,deployed=False,upstream=staged['upstream'],manifest=m,
             changed_upstream_core_files=changed,unchanged_keyboard_fifo_pmu_battery_rtc=True,
             module_embedded=False,product_mk61s_sources_compiled=False,option_byte_programming=False,
             largest_individual_static_frames=sorted(static_frames,key=lambda x:x['bytes'],reverse=True)[:8],
             static_frames_are_not_total_stack_bound=True,hardware_stack_and_uart_measurements_pending=True,
             i2c_expiry_fix=m.get('i2c_expiry_fix',False),power_status_protocol=m.get('power_status_protocol'),prior_hardware_hold_remains=True,
             tests={name:report['status']for name,report in reports.items()},
             flash_plan=plan,files={str(p.relative_to(ROOT)):sha(p)for p in files})
 (B/'review-packet.json').write_text(json.dumps(packet,indent=2)+'\n')
 print(json.dumps(dict(status=packet['status'],pinned_files=len(packet['files']),packet=str(B/'review-packet.json'),
                       packet_sha256=sha(B/'review-packet.json'),firmware_sha256=m['bin_sha256'],
                       flash_bytes=m['flash_image_bytes'],ram_globals=m['global_ram_bytes'],
                       ram_free_after_4k_stack=m['ram_unallocated_bytes'],erase_pages_in_unexecuted_plan=pages),indent=2))
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--build-dir',type=Path,default=B)
 args=parser.parse_args();B=args.build_dir.resolve();D=B/'source'
 if not B.is_relative_to(ROOT):parser.error('build directory must be inside the repository')
 main()
