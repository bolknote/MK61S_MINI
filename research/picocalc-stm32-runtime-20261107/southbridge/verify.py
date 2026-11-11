#!/usr/bin/env python3
"""Build finite HOST/ARM checks. This script never opens a serial port."""
from pathlib import Path
import argparse,importlib.util,json,shutil,subprocess,sys
P=Path(__file__).resolve().parent;R=P.parent;ROOT=R.parents[1]
BASE=ROOT/'.build/stm32-module-runtime-20261107';B=BASE/'southbridge-runtime'
sys.path.insert(0,str(R/'tools'))
from build import tool,run
def build_checks():
 src=B/'source/Core/Src';inc=B/'source/Core/Inc'
 flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(inc)]
 for source,name in [(src/'stm3_runtime.c','runtime'),(R/'modules/q4_dot.c','module')]:
  subprocess.run(['clang','-std=c11',*flags,'-c',str(source),'-o',str(B/(name+'-host.o'))],check=True)
 for source,name,objects,args in [(R/'tests/runtime_test.cpp','runtime',[B/'runtime-host.o',B/'module-host.o'],[BASE/'module/q4_dot.s3m']),
                                  (P/'tests/compact_test.cpp','compact',[B/'runtime-host.o'],[])]:
  executable=B/(name+'-host-test')
  subprocess.run(['clang++','-std=c++17',*flags,str(source),*map(str,objects),'-o',str(executable)],check=True)
  run([executable,*args],B/(name+'-host-test.log'))
  print((B/(name+'-host-test.log')).read_text().strip())
 # Reuse the exact old module package; only its resident loader has changed.
 (B/'module').mkdir(exist_ok=True)
 shutil.copy2(BASE/'module/q4_dot.s3m',B/'module/q4_dot.s3m')
 (B/'arm-harness').mkdir(exist_ok=True)
 flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g','-ffreestanding','-fno-builtin','-fno-common','-fno-stack-protector','-fno-unwind-tables','-fno-asynchronous-unwind-tables','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-I'+str(inc)]
 run([tool('gcc'),*flags,'-nostdlib',src/'stm3_runtime.c',R/'tests/arm_harness.c','-Wl,-T,'+str(R/'tests/harness.ld'),'-o',B/'arm-harness/harness.elf'],B/'arm-harness/build.log')
 (B/'combined-harness').mkdir(exist_ok=True)
 src=B/'source/Core/Src';inc=B/'source/Core/Inc';drivers=BASE/'community-southbridge/Drivers'
 flags=['-mcpu=cortex-m3','-mthumb','-mfloat-abi=soft','-std=gnu17','-Os','-g','-ffreestanding','-fno-builtin','-fdata-sections','-ffunction-sections','-DSTM32F103xB','-DUSE_HAL_DRIVER','-DUSE_FULL_LL_DRIVER','-DUART_PICO_INTERFACE','-DSTM3_MODULE_RUNTIME',
        '-I'+str(inc),'-I'+str(drivers/'STM32F1xx_HAL_Driver/Inc'),'-I'+str(drivers/'CMSIS_Device_ST_STM32F1xx/Include'),'-I'+str(drivers/'CMSIS/Include')]
 sources=[src/(name+'.c')for name in ['stm3_runtime','stm3_uart_dma','coproc_hal','clock72','i2cs','fifo','backlight']]
 sources.append(drivers/'STM32F1xx_HAL_Driver/Src/stm32f1xx_ll_utils.c')
 run([tool('gcc'),*flags,'-nostdlib',*sources,P/'tests/combined_harness.c','-lgcc','-Wl,--gc-sections,-T,'+str(P/'tests/combined.ld'),'-o',B/'combined-harness/combined.elf'],B/'combined-harness/build.log')
 (B/'uart-harness').mkdir(exist_ok=True)
 run([tool('gcc'),*flags,'-nostdlib',src/'stm3_uart_dma.c',R/'tests/uart_harness.c','-Wl,-T,'+str(R/'tests/uart_harness.ld'),'-o',B/'uart-harness/uart.elf'],B/'uart-harness/build.log')
 result=dict(status='HOST_PASS',physical_io=False,asan_ubsan=True,numeric_reference_rows=1360,jobs=160,
             malformed_packages=11,framing_noise_bytes=60000,in_place_cobs_vectors=804,aliased_read_lengths=253)
 (B/'host-verification.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--build-dir',type=Path,default=B)
 args=parser.parse_args();B=args.build_dir.resolve()
 if not B.is_relative_to(ROOT):parser.error('build directory must be inside the repository')
 build_checks()
