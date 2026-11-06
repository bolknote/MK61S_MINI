#!/usr/bin/env python3
"""Consume production C5 formatters with distinct CRC and PSRAM fault values."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def field(wire, name):
    # Existing CDC consumers require exactly one whitespace-delimited key
    # across the complete report. Substring matches would hide this bug.
    values = re.findall(r'(?:^|\s)' + re.escape(name) + r'=([^\s]+)', wire)
    if len(values) != 1:
        raise ValueError(f'{name}: expected one field, received {values}')
    return values[0]


class StatusFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='picocalc-status-fields-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.work = Path(cls.temp.name)
        main = (ROOT / 'ports/picocalc/main.cpp').read_text()
        calls = re.findall(r'std::printf\("PSRAM_BOOT_QPI_ATTEMPTS=[\s\S]*?\);', main)
        assert len(calls) == 1, 'Missing or ambiguous production PSRAM boot formatter'
        report = function((ROOT / 'ports/picocalc/firmware.cpp').read_text(), 'unsigned report(')
        cls.template = r'''
#include "firmware.hpp"
#include "psram.hpp"
#include <cstdio>
#include <cstring>
namespace picocalc::firmware {
using resident_firmware_format::Status;
constexpr u32 FAILURE_MAGIC=0x50434657;
struct Failure { u32 magic,inverse,status,expected,actual; } failure{};
Result boot;
Result verify() { return boot; }
REPORT
}
int main(int argc,char** argv) {
    using namespace picocalc;
    firmware::boot={resident_firmware_format::Status::VALID,0xC05E1BE3,0xC05E1BE3,1537024,938808,37};
    if(argc>1 && !std::strcmp(argv[1],"retained"))
        firmware::failure={firmware::FAILURE_MAGIC,~firmware::FAILURE_MAGIC,
            (u32)resident_firmware_format::Status::CRC_MISMATCH,0x11223344,0x55667788};
    psram::Statistics psram{};
    psram.boot.qpi_attempts=2;
    psram::probe_failure(psram.boot,psram::ProbePhase::COMPARE,true,0x00402001,0x7B,0xA9);
    psram::probe_failure(psram.boot,psram::ProbePhase::READ,false,0x007FFFFF,0xFF,0xFFFFFFFF);
    char out[1024];const unsigned used=firmware::report(out,sizeof(out),false);
    std::fwrite(out,1,used,stdout);
    PROBE
}
'''.replace('REPORT', report).replace('PROBE', calls[0])
        cls.current = cls.build('current', cls.template)

    @classmethod
    def build(cls, name, source):
        cpp = cls.work / (name + '.cpp')
        cpp.write_text(source)
        binary = cls.work / name
        command = [os.environ.get('CXX', 'clang++'), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-I' + str(ROOT / 'ports/picocalc'), '-I' + str(ROOT / 'code')]
        if os.environ.get('MK61_TEST_SANITIZERS') == '1':
            command += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        subprocess.run(command + [str(cpp), '-o', str(binary)], check=True)
        return binary

    @staticmethod
    def wire(binary, retained=False):
        return subprocess.run([str(binary)] + (['retained'] if retained else []),
                              check=True, capture_output=True, text=True).stdout

    def check_crc(self, wire):
        self.assertEqual(field(wire, 'FIRMWARE_CRC'), 'valid')
        self.assertEqual(field(wire, 'EXPECTED'), 'C05E1BE3')
        self.assertEqual(field(wire, 'ACTUAL'), 'C05E1BE3')

    def test_crc_fields_remain_unambiguous_with_psram_failure(self):
        wire = self.wire(self.current)
        self.check_crc(wire)
        self.assertEqual(field(wire, 'PSRAM_BOOT_QPI_ATTEMPTS'), '2')
        self.assertEqual(field(wire, 'PROBE_FAILURES'), '2')
        self.assertEqual(field(wire, 'FIRST_PHASE'), 'COMPARE')
        self.assertEqual(field(wire, 'FIRST_QPI'), '1')
        self.assertEqual(field(wire, 'PROBE_ADDRESS'), '00402001')
        self.assertEqual(field(wire, 'PROBE_EXPECTED'), '0000007B')
        self.assertEqual(field(wire, 'PROBE_ACTUAL'), '000000A9')
        self.assertEqual(field(wire, 'LAST_FAILURE'), 'READ')

    def test_retained_firmware_failure_has_its_own_fields(self):
        wire = self.wire(self.current, retained=True)
        self.check_crc(wire)
        self.assertEqual(field(wire, 'FIRMWARE_LAST_FAILURE'), 'crc-mismatch')
        self.assertEqual(field(wire, 'LAST_FAILURE_EXPECTED'), '11223344')
        self.assertEqual(field(wire, 'LAST_FAILURE_ACTUAL'), '55667788')
        self.assertEqual(field(wire, 'PROBE_EXPECTED'), '0000007B')
        self.assertEqual(field(wire, 'PROBE_ACTUAL'), '000000A9')

    def test_previous_probe_field_names_reproduce_guard_failure(self):
        source = self.template.replace('PROBE_EXPECTED=', 'EXPECTED=').replace('PROBE_ACTUAL=', 'ACTUAL=')
        binary = self.build('old-probe', source)
        for name in ('EXPECTED', 'ACTUAL'):
            with self.assertRaises(ValueError):
                field(self.wire(binary), name)

    def test_previous_retained_field_names_reproduce_guard_failure(self):
        source = self.template.replace('LAST_FAILURE_EXPECTED=', 'EXPECTED=').replace('LAST_FAILURE_ACTUAL=', 'ACTUAL=')
        binary = self.build('old-retained', source)
        for name in ('EXPECTED', 'ACTUAL'):
            with self.assertRaises(ValueError):
                field(self.wire(binary, retained=True), name)


if __name__ == '__main__':
    unittest.main()
