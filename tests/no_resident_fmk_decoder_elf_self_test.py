#!/usr/bin/env python3
"""Actual ARM ELF gate: fixed header allowed, full font parsing rejected."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "rust_types.h"
#define KEEP __attribute__((noipa, used))
volatile u32 observed;
volatile u32 input_address = 0x20000000U;
volatile u32 input_size = 1024;
#ifdef BIG_HEADER
namespace fmk {
KEEP bool plausibleHeader(const u8* bytes, usize size) {
  __asm__ volatile(".rept 128\n nop\n .endr");
  return size != 0 && bytes[0] != 0;
}
}
#else
#include "fmk_font.hpp"
#endif
#ifdef FACE_LEAK
namespace fmk {
KEEP bool Face::open(const u8* bytes, usize size) {
  observed += bytes[0] + size;
  return observed != 0;
}
}
#endif
#ifdef DECODE_LEAK
namespace fmk {
KEEP bool Face::decode(const Glyph&, u8* bytes, usize size) const {
  observed += size;
  return bytes != nullptr;
}
}
#endif
#ifdef COMPILER_LEAK
namespace fmk { namespace {
class Compiler { public: KEEP bool append(u8 byte) { observed += byte; return true; } };
}}
#endif
#ifdef LOOKALIKE_LEAK
namespace fmk { KEEP bool plausibleHeaderDecoder() { observed++; return true; } }
#endif
extern "C" KEEP void _start() {
  const u8* bytes = (const u8*) input_address;
  observed = fmk::plausibleHeader(bytes, input_size);
#ifdef FACE_LEAK
  observed += ((fmk::Face*) input_address)->open(bytes, input_size);
#endif
#ifdef DECODE_LEAK
  fmk::Glyph glyph = {};
  observed += ((fmk::Face*) input_address)->decode(glyph, (u8*) input_address, input_size);
#endif
#ifdef COMPILER_LEAK
  fmk::Compiler compiler; observed += compiler.append(1);
#endif
#ifdef LOOKALIKE_LEAK
  observed += fmk::plausibleHeaderDecoder();
#endif
  for(;;) {}
}
'''


def compiler_path():
    explicit = os.environ.get('ARM_NONE_EABI_GXX')
    if explicit:
        return Path(explicit)
    found = shutil.which('arm-none-eabi-g++')
    if found:
        return Path(found)
    for data in (os.environ.get('ARDUINO_DATA_DIR'),
                 str(Path.home() / '.arduino15'),
                 str(Path.home() / 'Library/Arduino15')):
        if data:
            matches = sorted(Path(data).glob(
                'packages/STMicroelectronics/tools/**/bin/arm-none-eabi-g++'))
            if matches:
                return matches[-1]
    return None


class NoResidentFmkDecoderElfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = compiler_path()
        if cls.compiler is None:
            raise unittest.SkipTest('ARM GCC unavailable')

    def gate(self, definition=None, lto=False, allow=False):
        with tempfile.TemporaryDirectory(prefix='mk61 FMK header ELF ') as directory:
            path = Path(directory)
            source, elf = path / 'fixture.cpp', path / 'fixture.elf'
            source.write_text(FIXTURE)
            command = [str(self.compiler), '-std=c++17', '-mcpu=cortex-m4',
                       '-mthumb', '-Oz', '-fno-exceptions', '-fno-rtti',
                       '-ffunction-sections', '-fdata-sections', '-nostdlib',
                       '-Wl,--gc-sections,-e,_start,-Ttext=0x08000000',
                       '-I' + str(ROOT / 'code'), str(source), '-o', str(elf)]
            if definition:
                command.insert(1, '-D' + definition)
            if lto:
                command.insert(1, '-flto')
            subprocess.run(command, check=True, capture_output=True, text=True)
            environment = dict(os.environ, ARM_NONE_EABI_NM=str(
                self.compiler.with_name('arm-none-eabi-nm')))
            options = ['--allow-fmk'] if allow else []
            return subprocess.run(['bash', str(ROOT / 'tests/check_no_resident_fmk_decoder_elf.sh'),
                                   *options, str(elf)], env=environment,
                                  capture_output=True, text=True)

    def test_real_header_passes_with_and_without_lto(self):
        for lto in (False, True):
            with self.subTest(lto=lto):
                result = self.gate(lto=lto)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_face_compiler_decode_and_lookalike_are_rejected(self):
        for definition in ('FACE_LEAK', 'DECODE_LEAK', 'COMPILER_LEAK', 'LOOKALIKE_LEAK'):
            for lto in (False, True):
                with self.subTest(definition=definition, lto=lto):
                    result = self.gate(definition, lto=lto)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn('compressed-font code leaked', result.stderr)

    def test_oversized_preflight_is_rejected(self):
        result = self.gate('BIG_HEADER')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('1..128 text bytes', result.stderr)

    def test_explicit_resident_parser_profile_remains_allowed(self):
        result = self.gate('FACE_LEAK', allow=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
