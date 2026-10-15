#!/usr/bin/env python3
"""Qualify the native and legacy USB layouts in both C and C++ on F401/F411."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


PROBE = r'''
#include <stddef.h>
#include "stm32f4_usbd_def.h"
#include "stm32f4_usbd_cdc.h"
#ifdef __cplusplus
#define CHECK static_assert
#define ALIGN alignof
#else
#define CHECK _Static_assert
#define ALIGN _Alignof
#endif
CHECK(sizeof(void *) == 4, "ARM pointer ABI");
CHECK(ALIGN(USBD_HandleTypeDef) == 4 && ALIGN(USBD_CDC_HandleTypeDef) == 4,
      "state stays naturally aligned");
CHECK(sizeof(USBD_SetupReqTypedef) == 8, "wire setup width");
CHECK(sizeof(((USBD_CDC_HandleTypeDef*)0)->RxLength) == 4 &&
      sizeof(((USBD_CDC_HandleTypeDef*)0)->TxLength) == 4, "full CDC lengths");
CHECK(offsetof(USBD_CDC_HandleTypeDef,RxLength)%4 == 0 &&
      offsetof(USBD_CDC_HandleTypeDef,TxLength)%4 == 0 &&
      offsetof(USBD_CDC_HandleTypeDef,RxBuffer)%4 == 0,
      "no unaligned counters or pointers");
#if MK61_USB_COMPACT_STATE
CHECK(sizeof(USBD_HandleTypeDef) == 96 && sizeof(USBD_EndpointTypeDef) == 4 &&
      sizeof(USBD_CDC_HandleTypeDef) == 28 && sizeof(USBD_ClassTypeDef) == 36,
      "native layout");
CHECK(sizeof(((USBD_HandleTypeDef*)0)->pClassDataCmsit) == sizeof(void *),
      "one authoritative class slot");
CHECK(offsetof(USBD_HandleTypeDef,dev_config_status)%2 == 0,
      "persistent status alignment");
CHECK(sizeof(((USBD_HandleTypeDef*)0)->control_in.rem_length) == 4 &&
      sizeof(((USBD_HandleTypeDef*)0)->control_out.total_length) == 4 &&
      sizeof(((USBD_HandleTypeDef*)0)->ep0_data_len) == 4, "full control lengths");
CHECK(sizeof(((USBD_HandleTypeDef*)0)->ep_in)/sizeof(USBD_EndpointTypeDef) == 4 &&
      sizeof(((USBD_HandleTypeDef*)0)->ep_out)/sizeof(USBD_EndpointTypeDef) == 4,
      "all eight endpoint directions retained");
#else
CHECK(sizeof(USBD_HandleTypeDef) == 252 && sizeof(USBD_EndpointTypeDef) == 20 &&
      sizeof(USBD_CDC_HandleTypeDef) == 36 && sizeof(USBD_ClassTypeDef) == 56,
      "legacy SDK ABI retained");
#endif
int layout_probe(void) { return sizeof(USBD_HandleTypeDef); }
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compile_commands', type=Path)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    entries = json.loads(args.compile_commands.read_text())
    entry = next(x for x in entries if Path(x['file']).name == 'stm32f4_usbd_core.c')
    raw = entry.get('arguments') or shlex.split(entry['command'])
    flags = []
    i = 1
    while i < len(raw):
        value = raw[i]
        if value.startswith(('-DSTM32F401', '-DSTM32F411', '-DMK61_NATIVE_RUNTIME=')):
            pass
        elif value.startswith(('-D', '-I', '-mcpu=', '-mthumb', '-mfpu=', '-mfloat-abi=')):
            flags.append(value)
        elif value == '-include':
            flags.extend(raw[i:i+2])
            i += 1
        i += 1
    results = []
    with tempfile.TemporaryDirectory(prefix='mk61-usb-layout-') as folder:
        source = Path(folder)/'layout.c'
        source.write_text(PROBE)
        for mcu in ('STM32F401xC', 'STM32F411xE'):
            for native in (0, 1):
                for language, standard in (('c', 'gnu11'), ('c++', 'gnu++17')):
                    command = [raw[0], *flags, '-D'+mcu,
                               f'-DMK61_NATIVE_RUNTIME={native}', '-Wall', '-Wextra',
                               '-Werror', '-x', language, '-std='+standard,
                               '-c', str(source), '-o', str(Path(folder)/'layout.o')]
                    subprocess.run(command, check=True, capture_output=True)
                    result = dict(mcu=mcu, native=native, language=language, status='PASS')
                    results.append(result)
                    print(result, flush=True)
        for extension in ('USBD_MAX_SUPPORTED_CLASS=2', 'USE_USBD_COMPOSITE=1'):
            command = [raw[0], *flags, '-DSTM32F411xE', '-DMK61_NATIVE_RUNTIME=1',
                       '-D'+extension, '-x', 'c', '-std=gnu11', '-c', str(source),
                       '-o', str(Path(folder)/'invalid.o')]
            result = subprocess.run(command, capture_output=True, text=True)
            assert result.returncode and 'compact USB state requires' in result.stderr, result.stderr
            results.append(dict(rejected=extension, status='PASS'))
            print(extension, 'rejected PASS', flush=True)
    if args.json:
        args.json.write_text(json.dumps(results, indent=2)+'\n')


if __name__ == '__main__':
    main()
