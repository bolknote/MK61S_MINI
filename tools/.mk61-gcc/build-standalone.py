#!/usr/bin/env python3
"""Build the owned STM32 runtime with GNU Arm GCC/CMake, without Arduino Core.

A reference compile database is optional metadata for matched experiments.
Normal builds select a board/MCU and may override individual MK61 definitions.
The project SDK supplies pinned CMSIS/LL and USB interface headers.
All compiled implementations are owned and versioned in this repository.
"""
import argparse
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import sys



def reference_features(entry, names):
    """Resolve board-dependent config defaults with the reference compiler."""
    command = entry.get('arguments') or shlex.split(entry['command'])
    arguments = []
    skip_next = False
    for argument in command[1:]:
        if skip_next:
            skip_next = False
        elif argument in ('-o', '-MF', '-MT', '-MQ'):
            skip_next = True
        elif argument not in ('-c', '-MD', '-MMD', '-MP', entry['file']):
            arguments.append(argument)
    source = '#include "config.h"\n'
    for name in names:
        if name != 'MK61_ENABLE_LTO':
            source += (f'#if {name}\nMK61_REFERENCE_{name} 1\n'
                       f'#else\nMK61_REFERENCE_{name} 0\n#endif\n')
    result = subprocess.run([command[0], *arguments,
        '-I' + str(Path(entry['file']).parent), '-E', '-P', '-x', 'c++', '-'],
        input=source, capture_output=True, text=True, check=True)
    values = dict(re.findall(r'^MK61_REFERENCE_(\w+) ([01])$',
                             result.stdout, re.MULTILINE))
    values['MK61_ENABLE_LTO'] = '1' if '-flto' in command else '0'
    if values.keys() != set(names):
        raise ValueError('reference config did not resolve every feature')
    return values

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--release-case')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--build-path', type=Path, required=True)
    parser.add_argument('--source-root', type=Path,
                        default=Path(__file__).resolve().parents[2])
    parser.add_argument('--profile')
    parser.add_argument('--mcu', choices=['f401', 'f411'])
    parser.add_argument('--define', action='append', default=[], metavar='NAME=VALUE')
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--toolchain', type=Path)
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be positive')
    root = args.source_root.resolve()
    contract = json.loads((root / 'tools/release-contract.json').read_text())
    versions = contract['toolchain']
    release_case = None
    if args.release_case:
        matches = [case for case in contract['cases'] if case['id'] == args.release_case]
        if len(matches) != 1:
            parser.error('unknown release case: ' + args.release_case)
        release_case = matches[0]
        if release_case['builder'] != 'gcc':
            parser.error('--release-case requires a native GCC case')
        if args.reference or args.define:
            parser.error('--release-case has fixed features; do not combine with --reference/--define')
        for name in ('mcu', 'profile'):
            given = getattr(args, name)
            if given and given != release_case[name]:
                parser.error('--' + name + ' differs from the release case')
            setattr(args, name, release_case[name])
    defaults = dict(
        MK61_ENABLE_FOCAL='1', MK61_ENABLE_TINYBASIC='1',
        MK61_ENABLE_WBMP_VIEWER='0', MK61_ENABLE_MARKDOWN_VIEWER='1',
        MK61_ENABLE_CHIP8='1', MK61_ENABLE_SETUP='1',
        MK61_FOCAL_AS_APP='1', MK61_TINYBASIC_AS_APP='1',
        MK61_WBMP_VIEWER_AS_APP='0', MK61_MARKDOWN_VIEWER_AS_APP='0',
        MK61_CHIP8_AS_APP='0', MK61_SETUP_AS_APP='0', MK61_EXPLORER_AS_APP='0',
        MK61_ENABLE_USB_SCREEN='1', MK61_EXTERNALIZE_USBDISK='0',
        MK61_WS0010_GRAPHICS_100X16='0', MK61_ENABLE_EXTENDED_FONT_SETTINGS='0',
        MK61_USER_EXPLORER_SHORTCUT='1', MK61_MATH_BACKEND='0',
        MK61_APP_LOCAL_FLOAT_MATH='0', MK61_F401_PRODUCT_BUILD='0',
        MK61_USE_COMPACT_LIBM='1', MK61_USE_NATIVE_EABI='1', MK61_USE_NATIVE_LIBC='1',
        MK61_REQUIRE_RESIDENT_CRC='1', MK61_ENABLE_LTO='1')
    reference_definitions = {}
    if args.reference:
        entries = json.loads(args.reference.read_text())
        entry = next(e for e in entries if e['file'].endswith('/terminal.cpp'))
        command = entry.get('arguments') or shlex.split(entry['command'])
        reference_definitions = dict(
            (v[2:].split('=', 1) + ['1'])[:2]
            for v in command if v.startswith('-D'))
        defaults.update(reference_features(entry, defaults))
        # This new native implementation defaults on when an older control
        # database predates the option; explicit old/new controls are retained.
        for option in ('MK61_USE_COMPACT_LIBM', 'MK61_USE_NATIVE_EABI', 'MK61_USE_NATIVE_LIBC'):
            if option not in reference_definitions:
                defaults[option] = '1'
    extra_definitions = []
    for definition in args.define:
        if '=' not in definition:
            parser.error('--define needs NAME=VALUE')
        name, value = definition.split('=', 1)
        if name not in defaults:
            if not re.fullmatch(r'MK61_[A-Z0-9_]+', name) or not re.fullmatch(r'[A-Za-z0-9_()+-]+', value):
                parser.error('invalid project feature definition: ' + definition)
            extra_definitions.append(definition)
        else:
            defaults[name] = value
    mcu = args.mcu or ('f401' if 'STM32F401xC' in reference_definitions else 'f411')
    profile = args.profile
    if not profile and reference_definitions:
        matches = [p['id'] for p in contract['profiles'] if all(
            name in reference_definitions for name in p['defines'])]
        # V2 has both the display flag and REVISION_V2; prefer that more
        # specific match over the V3 profile which shares only the display.
        if matches:
            specific = max(len(p['defines']) for p in contract['profiles'] if p['id'] in matches)
            matches = [p['id'] for p in contract['profiles'] if p['id'] in matches
                       and len(p['defines']) == specific]
        if len(matches) == 1:
            profile = matches[0]
    profile = profile or 'classic-v3'
    if profile not in [p['id'] for p in contract['profiles']]:
        parser.error('unknown profile: ' + profile)
    sys.path.insert(0, str(root / 'tools/.mk61-gcc'))
    from native_sdk import find_toolchain, validate_sdk, verify_toolchain_version
    try:
        sdk = validate_sdk(args.sdk or os.environ.get('MK61_GCC_SDK') or
                           root / 'third_party/stm32f4')
        toolchain = find_toolchain(root, versions['gnu_arm'], args.toolchain)
        verify_toolchain_version(toolchain, versions['gnu_arm'])
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    case_definitions = []
    if release_case:
        # Resolve the case's actual config defaults with the native header SDK,
        # never with board-package properties or an installed Arduino Core.
        includes = [root / 'code', root / 'tools/.mk61-gcc/standalone']
        includes += [sdk / name / 'include' for name in
                     ('cmsis', 'device', 'hal', 'usb-interface', 'usb')]
        profile_definitions = next(p['defines'] for p in contract['profiles'] if p['id'] == profile)
        case_definitions = release_case.get('defines', [])
        arguments = [str(toolchain / 'arm-none-eabi-g++'), '-std=gnu++17',
                     '-mcpu=cortex-m4', '-mthumb', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard',
                     '-DARDUINO=10607', '-DARDUINO_ARCH_STM32', '-DMK61_NATIVE_RUNTIME=1',
                     '-DUSBCON', '-DUSBD_USE_CDC', '-DUSE_FULL_LL_DRIVER',
                     '-DMK61_ENABLE_LOADABLE_MODULES=1', '-DMK61_REQUIRE_RESIDENT_CRC=1',
                     '-DMK61_USE_COMPACT_LIBM=1', '-DMK61_USE_NATIVE_EABI=1',
                     '-DMK61_USE_NATIVE_LIBC=1',
                     '-D' + ('STM32F411xE' if mcu == 'f411' else 'STM32F401xC')]
        arguments += ['-I' + str(path) for path in includes]
        arguments += ['-D' + flag for flag in [*profile_definitions, *case_definitions]]
        if release_case.get('optimization') == 'oslto':
            arguments += ['-flto']
        defaults.update(reference_features({'arguments': arguments,
            'file': str(root / 'code/terminal.cpp')}, defaults))
        if mcu == 'f401':
            mapping = dict(focal='MK61_ENABLE_FOCAL', basic='MK61_ENABLE_TINYBASIC',
                wbmp='MK61_ENABLE_WBMP_VIEWER', markdown='MK61_ENABLE_MARKDOWN_VIEWER',
                chip8='MK61_ENABLE_CHIP8', usb_screen='MK61_ENABLE_USB_SCREEN',
                ws0010_graphics='MK61_WS0010_GRAPHICS_100X16',
                extended_font_settings='MK61_ENABLE_EXTENDED_FONT_SETTINGS',
                user_explorer='MK61_USER_EXPLORER_SHORTCUT', math_backend='MK61_MATH_BACKEND',
                lto='MK61_ENABLE_LTO')
            for key, name in mapping.items():
                defaults[name] = str(release_case['features'][key])
            for name in ('FOCAL','TINYBASIC','WBMP_VIEWER','MARKDOWN_VIEWER','CHIP8','SETUP','EXPLORER'):
                defaults['MK61_' + name + '_AS_APP'] = '1'
            defaults['MK61_EXTERNALIZE_USBDISK'] = '1'
            defaults['MK61_F401_PRODUCT_BUILD'] = str(int(release_case['product']))
    if args.check:
        print('Native SDK:', sdk)
        print('GNU Arm:', toolchain)
        return
    out = args.build_path.resolve()
    out.mkdir(parents=True, exist_ok=True)
    configure = ['cmake', '-S', str(root / 'tools/.mk61-gcc'), '-B', str(out),
        '-G', 'Ninja', '-DCMAKE_TOOLCHAIN_FILE=' + str(root / 'tools/.mk61-gcc/arm-none-eabi.cmake'),
        '-DMK61_ARM_TOOLCHAIN_BIN=' + str(toolchain.resolve()),
        '-DMK61_PROJECT_ROOT=' + str(root), '-DMK61_SDK_ROOT=' + str(sdk),
        '-DMK61_PROFILE=' + profile, '-DMK61_TARGET_MCU=' + mcu,
        '-DMK61_GLOBAL_RAM_LIMIT=' + ('104857' if mcu == 'f411' else '52428')]
    configure += ['-D' + name + '=' + value for name, value in defaults.items()]
    if extra_definitions:
        configure += ['-DMK61_CASE_DEFINITIONS=' + ';'.join(extra_definitions)]
    if release_case:
        budgets = release_case['budgets']
        configure += ['-DMK61_CASE_DEFINITIONS=' + ';'.join(case_definitions),
                      '-DMK61_FLASH_MIN_HEADROOM=' + str(budgets['flash_min_headroom']),
                      '-DMK61_STACK_FRAME_LIMIT=' + str(budgets['stack_frame_limit'])]
        if 'ram_limit' in budgets:
            configure += ['-DMK61_GLOBAL_RAM_LIMIT=' + str(budgets['ram_limit'])]
    metadata = dict(mcu=mcu, profile=profile, features=defaults, release_case=args.release_case,
                    source_root=str(root), sdk=str(sdk.resolve()),
                    reference=str(args.reference) if args.reference else None,
                    extra_definitions=extra_definitions)
    (out / 'standalone-profile.json').write_text(json.dumps(metadata, indent=2) + '\n')
    subprocess.run(configure, check=True)
    subprocess.run(['cmake', '--build', str(out), '--parallel', str(args.jobs)], check=True)
    print('Owned runtime built; seal resident.bin before installation.')


if __name__ == '__main__':
    main()
