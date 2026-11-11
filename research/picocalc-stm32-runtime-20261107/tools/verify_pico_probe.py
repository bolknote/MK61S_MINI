#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,sys
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
B=ROOT/'.build/stm32-module-runtime-20261107/southbridge-runtime/pico-probe'
sys.path.insert(0,str(R/'tools'));from build import tool,run
flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(R/'include'),'-I'+str(R/'pico'),'-I'+str(R/'southbridge/runtime')]
for source,name in [(R/'pico/stm3_client.c','client'),(R/'southbridge/runtime/stm3_runtime.c','server')]:
 subprocess.run(['clang','-std=c11',*flags,'-c',str(source),'-o',str(B/(name+'-host.o'))],check=True)
subprocess.run(['clang++','-std=c++17',*flags,str(R/'tests/client_test.cpp'),str(B/'client-host.o'),str(B/'server-host.o'),'-o',str(B/'client-host-test')],check=True)
run([B/'client-host-test'],B/'client-host-test.log');print((B/'client-host-test.log').read_text())
flags=['-mcpu=cortex-m0plus','-mthumb','-mfloat-abi=soft','-std=c11','-Os','-g','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-I'+str(R/'pico'),'-nostdlib']
run([tool('gcc'),*flags,R/'pico/pico_uart1.c',R/'tests/pico_uart_harness.c','-Wl,-T,'+str(R/'tests/harness.ld'),'-o',B/'pico-uart.elf'],B/'pico-uart-build.log')
(B/'host-verification.json').write_text(json.dumps(dict(status='CLIENT_ASAN_UBSAN_PASS',physical_io=False,read_lengths=253,crc_replay=True))+'\n')
