#!/usr/bin/env python3
"""Compile real ARM fixtures to test STOP boundaries, LTO names and failures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#define KEEP __attribute__((noipa, used, externally_visible))
#ifndef ENABLED
#define ENABLED 1
#endif
#define CONFIG
#define ARDUINO_ARCH_STM32
#define USBCON
#define STM32F411xE
#define MK61_ENABLE_USB_POWER_OBSERVER 1
#define MK61_USB_SUSPEND_ENABLED ENABLED
#define MK61_DEEP_IDLE_ENABLED ENABLED
#define MK61_KEYBOARD_MINI
#define MK61_OLED1602_WS0010
#include "usb_power.hpp"
volatile unsigned long hardware[8];
volatile unsigned long observed;
namespace deep_idle { namespace {
#if ENABLED
static volatile unsigned long automatic_controller = 1;
#endif
}}
namespace usb_power { namespace {
#if ENABLED
static volatile unsigned short stop_arms;
#endif
}
#ifdef WEAK_PREPARE
__attribute__((weak))
#endif
PrepareResult prepare_stop(bool idle, u32 now) {
#ifdef ZERO_PREPARE
  return PrepareResult::ARMED;
#else
#if ENABLED
  stop_arms += !idle;
#endif
  for(unsigned long i = 0; i < 8; ++i) hardware[i] = now + i;
  return (hardware[2] & 1) != 0 ? PrepareResult::HOST_RESUMED : PrepareResult::ARMED;
#endif
}
StopCompletion finish_stop(bool host, bool keyboard) {
#ifdef ZERO_FINISH
  return {false, false};
#else
  for(unsigned long i = 0; i < 4; ++i) hardware[i] ^= host + keyboard;
  return {true, host};
#endif
}
bool stop_wake_pending() {
#ifdef ZERO_CLASSIFIER
  return false;
#else
  return (hardware[0] & (1UL << 18)) != 0;
#endif
}
}
#define CALLBACK(name) \
  extern "C" KEEP void USBD_LL_##name() { hardware[6]++; } \
  extern "C" KEEP void __wrap_USBD_LL_##name() { USBD_LL_##name(); }
CALLBACK(SetupStage)
CALLBACK(Reset)
CALLBACK(Suspend)
CALLBACK(Resume)
CALLBACK(DevConnected)
CALLBACK(DevDisconnected)
extern "C" KEEP void OTG_FS_WKUP_IRQHandler() { hardware[7]++; }
extern "C" KEEP void _start() {
#if ENABLED
  observed = deep_idle::automatic_controller;
#endif
#ifndef DETACHED_PREPARE
  observed += static_cast<unsigned char>(usb_power::prepare_stop(observed != 0, observed));
#endif
  observed += usb_power::stop_wake_pending();
  observed += usb_power::finish_stop(observed != 0, false).completed;
}
'''


def find_compiler():
    explicit = os.environ.get('ARM_NONE_EABI_GXX')
    if explicit:
        return Path(explicit)
    found = shutil.which('arm-none-eabi-g++')
    if found:
        return Path(found)
    for data in (os.environ.get('ARDUINO_DATA_DIR'),
                 str(Path.home() / '.arduino15'),
                 str(Path.home() / 'Library/Arduino15')):
        if not data:
            continue
        matches = sorted((candidate for pattern in ('arm-none-eabi-g++', 'arm-none-eabi-g++.exe')
            for candidate in Path(data).glob(
                'packages/STMicroelectronics/tools/**/bin/' + pattern)), reverse=True)
        if matches:
            return matches[0]
    return None


class UsbSuspendElfTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = find_compiler()
        if cls.compiler is None:
            raise unittest.SkipTest('ARM GCC unavailable for actual ELF regressions')

    def run_gate(self, definitions=(), lto=False, disabled=False, promoted=False):
        with tempfile.TemporaryDirectory(prefix='mk61 USB STOP ELF ') as temporary:
            base = Path(temporary)
            source, elf = base / 'fixture.cpp', base / 'fixture.elf'
            source.write_text(FIXTURE)
            arguments = [str(self.compiler), '-std=c++17', '-Os', '-mcpu=cortex-m4',
                         '-mthumb', '-fno-exceptions', '-fno-rtti', '-nostdlib',
                         '-Wl,-e,_start', '-I' + str(ROOT / 'code'),
                         *['-D' + value for value in definitions]]
            if lto:
                arguments.append('-flto')
            compiled = subprocess.run([*arguments, str(source), '-o', str(elf)],
                                      capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            bin_dir = self.compiler.parent
            suffix = '.exe' if self.compiler.name.endswith('.exe') else ''
            environment = {**os.environ,
                'ARM_NONE_EABI_NM': str(bin_dir / ('arm-none-eabi-nm' + suffix)),
                'ARM_NONE_EABI_OBJDUMP': str(bin_dir / ('arm-none-eabi-objdump' + suffix)),
                'ARM_NONE_EABI_CXXFILT': str(bin_dir / ('arm-none-eabi-c++filt' + suffix))}
            if promoted:
                # Model the exact GCC-private suffix before demangling; real
                # promotion depends on LTRANS partition count and TU layout.
                wrapper = base / 'nm with LTO promotion'
                wrapper.write_text('#!/usr/bin/env python3\n'
                    'import re, subprocess, sys\n'
                    f'output = subprocess.check_output([{environment["ARM_NONE_EABI_NM"]!r}, '
                    '*sys.argv[1:]], text=True)\n'
                    'for line in output.splitlines():\n'
                    '    if "automatic_controller" in line or "stop_arms" in line:\n'
                    '        line = re.sub(r"\\.lto_priv\\.[0-9]+$", "", line) + ".lto_priv.7"\n'
                    '    print(line)\n')
                wrapper.chmod(0o755)
                environment['ARM_NONE_EABI_NM'] = str(wrapper)
            command = ['bash', str(ROOT / 'tests/check_usb_suspend_elf.sh')]
            if disabled:
                command.append('--disabled')
            return subprocess.run([*command, str(elf)], env=environment,
                                  capture_output=True, text=True)

    def test_real_call_boundaries_with_and_without_lto(self):
        for lto in (False, True):
            with self.subTest(lto=lto):
                result = self.run_gate(lto=lto)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_lto_promoted_private_state_is_checked(self):
        result = self.run_gate(lto=True, promoted=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_gate(lto=True, promoted=True, disabled=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('automatic STOP controller in disabled profile', result.stderr)

    def test_weak_preparation_is_rejected(self):
        result = self.run_gate(('WEAK_PREPARE',))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing strong USB STOP preparation', result.stderr)

    def test_retained_but_uncalled_preparation_is_rejected(self):
        result = self.run_gate(('DETACHED_PREPARE',), lto=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no actual call to USB STOP preparation', result.stderr)

    def test_zero_stubs_are_rejected_even_when_called(self):
        for definition in ('ZERO_PREPARE', 'ZERO_FINISH', 'ZERO_CLASSIFIER'):
            with self.subTest(definition=definition):
                result = self.run_gate((definition,), lto=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('empty or trivial', result.stderr)

    def test_disabled_fixture_passes_without_state(self):
        result = self.run_gate(('ENABLED=0',), lto=True, disabled=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
