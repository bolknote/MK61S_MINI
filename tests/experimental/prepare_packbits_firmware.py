#!/usr/bin/env python3
"""Build matched resident-Flash PackBits qualification images in snapshots.

The repository firmware is not instrumented. Both snapshots get identical
private DWT points; only repeated_count differs between the two variants.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]

# Keep the measured scalar implementation independent of the current HEAD:
# after the optimization is committed, HEAD contains the candidate as well.
BASELINE_REPEATED_COUNT = '''static usize repeated_count(const u8* input, usize size, usize at) {
  usize count = 1;
  while(at + count < size && count < 128 &&
        input[at + count] == input[at]) count++;
  return count;
}'''


def replace_once(text, old, new):
    assert text.count(old) == 1, f'qualification anchor changed: {old[:80]!r}'
    return text.replace(old, new, 1)


def function_span(text):
    match = re.search(r'\busize repeated_count\(', text)
    assert match
    start = text.rfind('\nstatic ', 0, match.start()) + 1
    brace = text.index('{', match.start())
    depth = 1
    at = brace + 1
    while depth:
        if text[at] == '{': depth += 1
        if text[at] == '}': depth -= 1
        at += 1
    return start, at


def select_protocol(folder, candidate):
    path = folder/'usb_screen_protocol.cpp'
    text = path.read_text()
    start, end = function_span(text)
    if candidate:
        assert 'always_inline' in text[start:end], 'candidate must be the inline word scan'
    else:
        text = text[:start] + BASELINE_REPEATED_COUNT + text[end:]
    path.write_text(text)


def instrument(folder):
    header = folder / 'dwt_profiler.hpp'
    text = header.read_text()
    text = replace_once(text, '  COUNT\n};',
        '  USB_PACKBITS,\n  USB_FRAME_PREPARE,\n'
        '  USB_RECT_PREPARE,\n  USB_PACKET_PREPARE,\n  COUNT\n};')
    header.write_text(text)
    profiler = folder / 'dwt_profiler.cpp'
    text = profiler.read_text()
    text = replace_once(text, '    case Point::COUNT:              break;',
        '    case Point::USB_PACKBITS:      return "usb.packbits";\n'
        '    case Point::USB_FRAME_PREPARE: return "usb.prepare";\n'
        '    case Point::USB_RECT_PREPARE:  return "usb.rect";\n'
        '    case Point::USB_PACKET_PREPARE:return "usb.packet";\n'
        '    case Point::COUNT:              break;')
    profiler.write_text(text)
    protocol = folder / 'usb_screen_protocol.cpp'
    text = protocol.read_text()
    text = replace_once(text, '#include "usb_screen_protocol.hpp"',
        '#include "usb_screen_protocol.hpp"\n#include "dwt_profiler.hpp"')
    text = replace_once(text,
        '                       usize& output_size) {\n  output_size = 0;\n'
        '  if((input == NULL && input_size != 0) || output == NULL) {',
        '                       usize& output_size) {\n'
        '  MK61_PROFILE_SCOPE(dwt_profiler::Point::USB_PACKBITS);\n'
        '  output_size = 0;\n'
        '  if((input == NULL && input_size != 0) || output == NULL) {')
    protocol.write_text(text)
    screen = folder / 'usb_screen.cpp'
    text = screen.read_text()
    text = replace_once(text, 'static bool beginFrame(void) {',
        'static bool beginFrame(void) {\n'
        '  MK61_PROFILE_SCOPE(dwt_profiler::Point::USB_FRAME_PREPARE);')
    # Scope RECT only around encode_rect_payload, keeping it disjoint from
    # queuePacket. PACKBITS is nested in RECT and must not be added twice.
    old = '''      if(usb_screen_protocol::encode_rect_payload(
           session->frame_id, area, pixels, session->rect_payload,
           sizeof(session->rect_payload), payload_size, codec) !=
         usb_screen_protocol::Status::OK) {'''
    new = '''      usb_screen_protocol::Status encode_status;
      {
        MK61_PROFILE_SCOPE(dwt_profiler::Point::USB_RECT_PREPARE);
        encode_status = usb_screen_protocol::encode_rect_payload(
           session->frame_id, area, pixels, session->rect_payload,
           sizeof(session->rect_payload), payload_size, codec);
      }
      if(encode_status != usb_screen_protocol::Status::OK) {'''
    text = replace_once(text, old, new)
    # Actual outgoing packets include CRC16, COBS and envelope preparation.
    needle = 'static bool queuePacket('
    start = text.index(needle)
    brace = text.index('{', start)
    text = text[:brace+1] + '\n  MK61_PROFILE_SCOPE(dwt_profiler::Point::USB_PACKET_PREPARE);' + text[brace+1:]
    screen.write_text(text)


def run(command, env):
    subprocess.run([str(x) for x in command], check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--flags', type=Path, required=True)
    parser.add_argument('--variant', choices=('baseline', 'candidate'), required=True)
    parser.add_argument('--source-dir', type=Path, default=ROOT/'code',
                        help='immutable common code snapshot, including font repair')
    parser.add_argument('--no-instrument', action='store_true',
                        help='build a normal image without private DWT points')
    parser.add_argument('--mcu', choices=('f401','f411'), default='f411')
    args = parser.parse_args()
    out = args.output_dir.resolve() / args.variant
    sketch = out / 'mk61s-M'
    assert not sketch.exists(), 'use a new snapshot directory'
    shutil.copytree(args.source_dir, sketch)
    select_protocol(sketch, args.variant == 'candidate')
    if not args.no_instrument: instrument(sketch)
    flags = args.flags.read_text().strip()
    if not args.no_instrument:
        flags = flags.replace('-DMK61_ENABLE_DWT_PROFILER=0','-DMK61_ENABLE_DWT_PROFILER=1')
        if '-DMK61_ENABLE_DWT_PROFILER=1' not in flags: flags += ' -DMK61_ENABLE_DWT_PROFILER=1'
    env = dict(os.environ, SOURCE_DATE_EPOCH='1791450000')
    # The measured device profile is -Os without LTO. Library/core versions
    # come from the same installed, release-qualified STM32 Arduino package.
    board, optimization, maximum = ('BLACKPILL_F401CC','oslto',262144) if args.mcu=='f401' else ('BLACKPILL_F411CE','osstd',524288)
    fqbn = f'STMicroelectronics:stm32:GenF4:pnum={board},upload_method=dfuMethod,xserial=none,usb=CDCgen,opt={optimization}'
    layout = subprocess.check_output(['arduino-cli', 'compile', '--fqbn', fqbn,
        '--show-properties=expanded', '--build-path', str(out/'properties'), str(sketch)],
        env=env, text=True)
    properties = dict(line.split('=', 1) for line in layout.splitlines() if '=' in line)
    linker = out / 'portable.ld'
    run(['python3', ROOT/'tools/.mk61-gcc/portable-layout.py',
         Path(properties['build.variant.path'])/properties['build.ldscript'], linker], env)
    link_flags = '-Wl,--wrap=USBD_CDC_ClearBuffer,--wrap=USBD_LL_SetupStage,--wrap=USBD_LL_Reset,--wrap=USBD_LL_Suspend,--wrap=USBD_LL_Resume,--wrap=USBD_LL_DevConnected,--wrap=USBD_LL_DevDisconnected'
    link_flags += ' -Wl,--default-script=' + str(linker)
    command = ['arduino-cli', 'compile', '--fqbn', fqbn, '--jobs', '8',
        '--build-path', out/'build', '--build-property', 'compiler.cpp.extra_flags='+flags,
        '--build-property', 'compiler.c.extra_flags=-DHAL_UART_MODULE_ONLY -DUSBD_CLASS_USER_STRING_DESC=0',
        '--build-property', 'compiler.c.elf.extra_flags='+link_flags, sketch]
    if args.mcu=='f401':
        command[-1:-1] = ['--build-property',
            'recipe.hooks.linking.prelink.20.pattern=python3 "'+str(ROOT/'tools/.mk61-gcc/protect-usb-lto.py')+'" "{build.path}" "{build.core.path}/../../libraries/USBDevice" "{compiler.path}{compiler.c.cmd}" {compiler.c.flags} {build.info.flags} {compiler.c.st_extra_flags} {compiler.c.extra_flags} {build.st_extra_flags} {build.extra_flags} {compiler.arm.cmsis.c.flags} "-I{build.core.path}" "-I{build.variant.path}"']
    (out/'build-command.json').write_text(json.dumps([str(x) for x in command],indent=2)+'\n')
    run(command, env)
    firmware = out/'build/mk61s-M.ino.bin'
    run(['bash', ROOT/'tools/seal-firmware.sh', 'seal', '--max-size', maximum, firmware], env)
    run(['bash', ROOT/'tools/seal-firmware.sh', 'check', '--max-size', maximum, firmware], env)
    run(['python3', ROOT/'tools/seal-firmware-elf.py', '--bin', firmware,
         '--elf', out/'build/mk61s-M.ino.elf',
         '--compile-commands', out/'build/compile_commands.json'], env)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sketch.iterdir() if p.is_file()}
    (out/'source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')


if __name__ == '__main__':
    main()
