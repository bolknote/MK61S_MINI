#!/usr/bin/env python3
"""Real ARM VMSTORE prefilter/source-CRC/full-load gates; no device writes."""
import argparse
import json
import struct
import tempfile
import zlib
from pathlib import Path

from unicorn.arm_const import UC_ARM_REG_SP
from run_app_flow_arm_tests import FlowMachine, FLOW_STEP, LANGUAGE_FLOW_MAGIC
from run_language_vm_arm_tests import package
from run_portable_system_arm_tests import Elf, ROOT, run


def container(source, image, compiler, language, **changes):
    """Independent literal-only C6 encoder; the ARM APP validates all CRCs."""
    key = dict(compiler_crc=zlib.crc32(compiler[:60]), source_crc=zlib.crc32(source),
               source_id=42, source_size=len(source), version=image[4])
    key.update(changes)
    prefix = struct.pack('<4sIIHHHHBBH', b'VMC1', key['compiler_crc'], key['source_crc'],
                         key['source_id'], key['source_size'], len(image), key['version'], language, 1, 0)
    entry = (24+len(image)+3)&~3
    plain = prefix+image+bytes(entry-24-len(image))+bytes.fromhex('05207047')
    payload = bytearray()
    control = mask = 0
    def bit(value):
        nonlocal control, mask
        if not mask:
            control = len(payload); payload.append(0); mask = 128
        if value: payload[control] |= mask
        mask >>= 1
    def gamma(value, invert=False):
        for value_bit in bin(value)[3:]:
            bit(False); bit((value_bit == '1') != invert)
        bit(True)
    gamma(len(plain)); payload.extend(plain); bit(True); gamma(256, True)
    header = bytearray(struct.pack('<8sHHHBB10IHHI', b'MK61APP\0', 1, 64, 6, 4, 1,
        5, 0x20000000, len(payload), len(plain), len(plain), entry, len(payload), 0,
        zlib.crc32(payload), zlib.crc32(plain), 0, 0, 0))
    struct.pack_into('<I', header, 60, zlib.crc32(header[:60]))
    return bytes(header+payload)


class StoreMachine(FlowMachine):
    def __init__(self, *args):
        super().__init__(*args)
        self.partitioned = True
        self.fault = None
        self.call_timeout_us = 60_000_000
        self.call_instruction_limit = 100_000_000

    def hook(self, uc, address, size, context):
        if (address not in self.callbacks and address not in self.basic_display and
                address not in (self.syscall&~1, self.binary_stop, self.debug_capability_return) and
                (not self.float_return or address != self.float_return[0])):
            self.stage_peaks[self.stage] = max(self.stage_peaks.get(self.stage, 0),
                self.stack_top-uc.reg_read(UC_ARM_REG_SP))
            return
        return super().hook(uc, address, size, context)

    def system(self, op, a, b, c, p):
        if op == 8:
            inode = {'/System/BASIC.APP':101, '/System/FOCAL.APP':102,
                     '/System/VMCache/VMSTORE.APP':43}.get(self.string(c))
            if inode in self.files and self.file(p, inode): return 0
            return 4
        result = super().system(op, a, b, c, p)
        if op == 37 and a == 5 and self.fault:
            if self.fault == 'revision': self.resource_revision += 1
            return 0  # Includes a late failure after bytes reached the loan.
        return result


def attempt(args, packed, address, language, source, image, compiler, record, expected, fault=None):
    m = StoreMachine(args.resident_elf, True, address)
    m.files[42] = (3 if language == 1 else 2, 'SOURCE', source)
    m.files[43] = (8, 'VMSTORE', args.app.read_bytes())
    m.files[101 if language == 1 else 102] = (8, 'COMPILER', compiler)
    if record is not None: m.files[44] = (8, 'VMC-002a', record)
    m.load(packed); m.fault = fault
    context, step, output = m.input+768, m.input+1120, m.input+1280
    values = m.workspace+4176
    tail = b'\x5A'*4016
    m.uc.mem_write(values, tail)
    m.uc.mem_write(context, bytes(240)); m.put(context, LANGUAGE_FLOW_MAGIC, 0x20A if language == 1 else 0x106)
    m.put(context+76, values)
    m.uc.mem_write(context+232, struct.pack('<HB', 42, language))
    def step_at(phase):
        m.uc.mem_write(step, bytes(48)); m.put(step, 48, 1, context, 240)
        m.uc.mem_write(step+16, struct.pack('<HBBI', 43, 4, 0, phase))
        assert m.call(FLOW_STEP, step) == 1
        assert m.words(step, 4) == (48, 1, context, 240)
        assert not m.depth and bytes(m.uc.mem_read(values, 4016)) == tail
    step_at(0x200)
    reads = [row for row in m.trace if row[0] == 'source_read' and row[1] == 42]
    if expected == 'early': assert not reads
    else:
        count = 1 if len(source) <= 4176 else (len(source)+255)//256
        if fault: count = 1
        assert len(reads) == count, (expected, len(source), reads, m.trace[-20:])
        assert all(m.workspace <= row[3] and row[3]+row[4] <= m.workspace+4176 for row in reads)
    action = m.words(step+32, 1)[0]
    if expected in ('early', 'source'):
        assert action == 1
        assert struct.unpack('<HBBI', m.uc.mem_read(step+24, 8)) == (0xFFFF, 2 if language == 1 else 1, 0, 0x100)
    else:
        assert action == 2 and m.words(step+36, 1)[0] == 0x201
        assert m.words(context+48, 2) == (len(image), 1664)
        m.put(context+56, output)
        m.uc.mem_write(output, b'\xCC'*len(image))
        # LOAD_RESERVED updates only the selected source ID in retained banks.
        if expected == 'hit':
            changed = bytearray(tail); struct.pack_into('<H', changed, 4+2*(language-1), 42); tail = bytes(changed)
        step_at(0x201)
        if expected == 'hit':
            assert m.words(step+32, 1)[0] == 1
            assert bytes(m.uc.mem_read(output, len(image))) == image
        else:
            assert m.words(step+32, 1)[0] == 2  # Bad payload: discard BUILDING, never commit.
            assert bytes(m.uc.mem_read(output, len(image))) == b'\xCC'*len(image)
    assert all(size <= 4176 for _, size in m.workspace_requests)
    return dict(address=address, language=language, source_bytes=len(source), expected=expected,
                fault=fault, reads=len(reads), stack_peak=max(m.stage_peaks.values()))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--resident-elf', type=Path, required=True)
    ap.add_argument('--app', type=Path, required=True)
    ap.add_argument('--system', type=Path, required=True)
    ap.add_argument('--report-file', type=Path)
    args = ap.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix='mk61-vmstore-arm-') as directory:
        work = Path(directory); reader = work/'reader'; probe = work/'probe'
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'), ROOT/'tests/portable_app_format_self_test.cpp',
             ROOT/'code/loadable_module_format.cpp', ROOT/'code/zx0.cpp', '-o', reader])
        run(['c++','-std=c++17','-O2','-I'+str(ROOT/'code'), ROOT/'tools/language_vm_probe.cpp',
             ROOT/'code/language_bytecode.cpp', ROOT/'code/language_vm.cpp', ROOT/'code/zx0_encode.cpp', '-o', probe])
        packed = package(reader, args.app, Elf(args.resident_elf), work, 'application')
        for language in (1,2):
            compiler = (args.system/('BASIC.APP' if language == 1 else 'FOCAL.APP')).read_bytes()
            for length in (3072,4176,4177):
                head = b'10 REM ' if language == 1 else b'1.01 C '
                end = b'\n20 A=42\n30 END\n' if language == 1 else b'\n1.02 S A=42;E\n'
                source = head+b'x'*(length-len(head)-len(end))+end
                text, binary = work/'source.txt', work/'source.bvm'; text.write_bytes(source)
                run([probe, 'basic' if language == 1 else 'focal', text, binary]); image = binary.read_bytes()
                record = container(source,image,compiler,language)
                for address in range(3):
                    rows.append(attempt(args,packed,address,language,source,image,compiler,record,'hit'))
                if length != 3072: continue
                wrong_header = bytearray(record); wrong_header[60] ^= 1
                wrong_body = bytearray(record); wrong_body[-1] ^= 1
                cases = [(None,'early',None),(b'bad','early',None),(bytes(wrong_header),'early',None),
                    (container(source,image,compiler,language,compiler_crc=zlib.crc32(compiler[:60])^1),'early',None),
                    (container(source,image,compiler,language,source_size=len(source)+1),'early',None),
                    (container(source,image,compiler,language,version=0),'early',None),
                    (container(source,image,compiler,language,source_crc=zlib.crc32(source)^1),'source',None),
                    (bytes(wrong_body),'payload',None),(record,'source','io'),(record,'source','revision')]
                for data, expected, fault in cases:
                    rows.append(attempt(args,packed,0,language,source,image,compiler,data,expected,fault))
    report = dict(status='PASS', runs=rows, source_prefix_bytes=4176, retained_values_bytes=4016,
                  note='Real ARM APP at three addresses; storage/allocator fixtures, not hardware timings.')
    if args.report_file: args.report_file.write_text(json.dumps(report,indent=2)+'\n')
    print('VMSTORE ARM: metadata-only misses, one-read small CRC, large paging, source/I/O/epoch faults, full CRC, retained values and three addresses PASS',flush=True)


if __name__ == '__main__': main()
