#!/usr/bin/env python3
"""Qualify the new M4 carrier/overlay/wire on HOST, with synthetic time only.

This does not repeat the previous 620640-call campaign. It checks the new
Flash overlay placement, four new packed carriers, their file protocol and
negative first-fault/context/timer guards. No serial/USB module is imported.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT / 'tests')]
from prepare import FLASH_BASE, FLASH_BYTES, GUARD, overlay_snapshot, pin, sealed_info
from wire import (FUNCTIONS, HEADER_WORDS, REPORT_BYTES, ROW_BYTES, parse_report,
                  parse_request, request)
from check_stm32_vectors import ElfImage
from build import load_template

CTX_ADDRESSES = [0x40023800, 0x40023804, 0x40023808, 0x40023c00, 0xe000ed14, 0xe000ed88]
CTX = [0x03010083, 0x24403019, 0x940a, 0x705, 0x200, 0xf00000]


def rejects(fn, what):
    try:
        fn()
    except ValueError:
        return 1
    raise AssertionError('guard did not reject: ' + what)


def corrected_request(raw, **changes):
    words = list(struct.unpack('<16I', raw))
    for key, value in changes.items():
        words[int(key)] = value
    words[14] = zlib.crc32(struct.pack('<14I', *words[:14])) & 0xffffffff
    return struct.pack('<16I', *words)


def host_guards(template):
    count = 0
    original = Path(template['resident_bin']['path']).read_bytes()
    snapshot = original + b'\xff' * (FLASH_BYTES - len(original))
    fixture = Path(template['fixture']['path']).read_bytes()
    start = template['fixture_base'] - FLASH_BASE
    overlaid = overlay_snapshot(snapshot, original, template['fixture_base'], fixture)
    assert overlaid[:start] == snapshot[:start] and overlaid[start + len(fixture):] == snapshot[start + len(fixture):]
    count += rejects(lambda: overlay_snapshot(snapshot[:-1], original, template['fixture_base'], fixture), 'partial original')
    changed = bytearray(snapshot); changed[0] ^= 1
    count += rejects(lambda: overlay_snapshot(changed, original, template['fixture_base'], fixture), 'wrong resident')
    changed = bytearray(snapshot); changed[start] = 0
    count += rejects(lambda: overlay_snapshot(changed, original, template['fixture_base'], fixture), 'unknown occupied tail')
    count += rejects(lambda: overlay_snapshot(overlaid, original, template['fixture_base'], fixture), 'overlay replay')
    count += rejects(lambda: overlay_snapshot(snapshot, original, FLASH_BASE, fixture), 'resident overwrite')
    count += rejects(lambda: overlay_snapshot(snapshot, original, template['fixture_base'] + 1, fixture), 'unaligned code')
    count += rejects(lambda: overlay_snapshot(snapshot, original, FLASH_BASE + FLASH_BYTES - 16, fixture), 'Flash overflow')
    changed = bytearray(original); changed[-1] ^= 1
    count += rejects(lambda: sealed_info(changed), 'bad resident seal')
    good = request(template, 1, 115, CTX)
    assert parse_request(good, template)['count'] == 2
    for raw in [good[:-1], good + b'\0', bytes([good[0] ^ 1]) + good[1:],
                corrected_request(good, **{'2': 2}), corrected_request(good, **{'3': 1149}),
                corrected_request(good, **{'4': 10}), corrected_request(good, **{'5': 114}),
                corrected_request(good, **{'6': 1}), corrected_request(good, **{'15': 1})]:
        count += rejects(lambda raw=raw: parse_request(raw, template), 'invalid request')
    return dict(overlay_and_request_negative_guards=count,
                synthetic_overlay_bytes=len(fixture), original_prefix_preserved=True, private_snapshots_copied=False)


def decoder(output):
    path = output / 'decode-m4-app'
    command = ['c++', '-std=c++17', '-O2', '-I' + str(ROOT / 'code'),
               str(ROOT / 'tests/portable_app_format_self_test.cpp'),
               str(ROOT / 'code/loadable_module_format.cpp'), str(ROOT / 'code/zx0.cpp'), '-o', str(path)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return path, command


class Machine:
    def __init__(self, template, app, decoded, base):
        from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE, UC_HOOK_MEM_READ
        import unicorn.arm_const as arm
        self.arm = arm
        self.template, self.app, self.base = template, app, base
        self.elf = ElfImage(Path(app['ELF']['path']))
        self.origin = app['report']['load_address']
        self.packed = Path(app['APP']['path']).read_bytes()
        self.entry = struct.unpack_from('<I', self.packed, 36)[0]
        self.u = Uc(UC_ARCH_ARM, UC_MODE_MCLASS | UC_MODE_THUMB)
        self.u.ctl_set_cpu_model(arm.UC_CPU_ARM_CORTEX_M4)
        self.u.mem_map(FLASH_BASE, FLASH_BYTES)
        self.u.mem_map(0x20000000, 0x20000)
        self.u.mem_map(0x40023000, 0x1000)
        self.u.mem_map(0xe0001000, 0x1000)
        self.u.mem_map(0xe000e000, 0x1000)
        ElfImage(Path(template['resident_elf']['path'])).load(self.u)
        self.u.mem_write(template['fixture_base'], Path(template['fixture']['path']).read_bytes())
        self.u.mem_write(base, decoded)
        self.stop, self.api, self.services = FLASH_BASE + 0x7ff00, FLASH_BASE + 0x7e000, FLASH_BASE + 0x7e100
        self.stubs = {name: FLASH_BASE + 0x7e200 + i * 16 for i, name in enumerate(
            ['query', 'call', 'millis', 'service', 'file_size', 'file_read', 'unexpected'])}
        for address in self.stubs.values():
            self.u.mem_write(address, b'\x70\x47')
        callbacks = [self.stubs['unexpected'] | 1] * 24
        for index, name in [(0, 'millis'), (1, 'service'), (13, 'file_size'), (14, 'file_read'), (23, 'query')]:
            callbacks[index] = self.stubs[name] | 1
        self.u.mem_write(self.api, struct.pack('<IHHI24I', 0x31505041, 1, 108, 33, *callbacks))
        self.u.mem_write(self.services, struct.pack('<IHH5I', 0x31535953, 2, 28, 0,
            self.stubs['call'] | 1, 0, 0, template['runtime_address']))
        for address, value in zip(CTX_ADDRESSES, CTX):
            self.put(address, value)
        self.put(0xe000ed00, 0x410fc241)
        self.put(0xe0001000, 0x40000000)
        self.put(0xe000edfc, 0x800)
        self.counter = 0xffffffe0
        self.millis = 0
        self.stopped_tick = self.stopped_wall = False
        self.change_context_on_target = False
        self.corrupt_target_return = False
        self.input = b''
        self.output = None
        self.target_calls = Counter()
        self.io = []
        self.dwt_counter_writes = 0

        def hook(uc, address, size, user):
            del size, user
            name = next(k for k, v in self.stubs.items() if v == address)
            values = [uc.reg_read(getattr(arm, 'UC_ARM_REG_R' + str(i))) for i in range(4)]
            if name == 'query':
                assert values[:2] == [1, 2]
                result = self.services
            elif name == 'call':
                operation, a, b, c = values
                payload = self.get(uc.reg_read(arm.UC_ARM_REG_SP))
                if operation == 26:
                    result = 258
                elif operation == 8:
                    assert a == 0xffff and b == 11
                    assert self.cstring(c) == template['root_namespace'] + '/INPUT.bin'
                    uc.mem_write(payload, struct.pack('<5I32s', 7, 9, 64, 11, 0, b'INPUT'))
                    self.io.append('resolve-owned-input'); result = 0
                elif operation == 9:
                    assert a == 9 and b == 0xffff and c == 11
                    name_ptr, data, n, inode = struct.unpack('<4I', uc.mem_read(payload, 16))
                    assert self.cstring(name_ptr) == 'RESULT' and inode == 0xffff and n == REPORT_BYTES
                    assert self.output is None, 'APP writes its report more than once'
                    self.output = bytes(uc.mem_read(data, n)); self.io.append('write-once-owned-result'); result = 1
                else:
                    raise AssertionError('unexpected service operation: ' + str(values))
            elif name == 'millis':
                if not self.stopped_wall:
                    self.millis = (self.millis + 1) & 0xffffffff
                    if not self.stopped_tick:
                        self.counter = (self.counter + 96000) & 0xffffffff
                result = self.millis
            elif name == 'service':
                result = 0
            elif name == 'file_size':
                assert values[0] == 7; result = len(self.input)
            elif name == 'file_read':
                assert values[0] == 7 and values[1] == 0 and values[3] == 64
                uc.mem_write(values[2], self.input[:64]); self.io.append('read-owned-input'); result = min(64, len(self.input))
            else:
                raise AssertionError('unexpected API access: ' + str(values))
            uc.reg_write(arm.UC_ARM_REG_R0, result)

        for address in self.stubs.values():
            self.u.hook_add(UC_HOOK_CODE, hook, begin=address, end=address)

        def tick_read(uc, access, address, size, value, user):
            del access, value, user
            assert address == 0xe0001004 and size == 4
            if not self.stopped_tick:
                self.counter = (self.counter + 17) & 0xffffffff
            uc.mem_write(address, struct.pack('<I', self.counter))

        self.u.hook_add(UC_HOOK_MEM_READ, tick_read, begin=0xe0001004, end=0xe0001007)
        targets = {}
        for leaf in template['leaves']:
            name = 'st_' + leaf['name'] if leaf['name'].endswith('_control') else leaf['symbol']
            if name in self.elf.symbols:
                targets[(self.elf.symbols[name] & ~1) + base - self.origin] = name
            targets[template['fixture_base'] + leaf['offset']] = 'Flash:' + name
        targets[template['actual_native_address'] & ~1] = 'real-runtime18-native'
        targets[(self.elf.symbols['strchr'] & ~1) + base - self.origin] = 'public-strchr'

        def target_hook(uc, address, size, user):
            del size, user
            self.target_calls[targets[address]] += 1
            if self.change_context_on_target:
                self.put(CTX_ADDRESSES[0], CTX[0] ^ 1)
                self.change_context_on_target = False
            if self.corrupt_target_return:
                # One injected wrong return before executing the leaf. No
                # later target is allowed to run after the carrier sees it.
                uc.reg_write(arm.UC_ARM_REG_R0, 0)
                uc.reg_write(arm.UC_ARM_REG_PC, uc.reg_read(arm.UC_ARM_REG_LR))
                self.corrupt_target_return = False

        for address in targets:
            self.u.hook_add(UC_HOOK_CODE, target_hook, begin=address, end=address)

    def put(self, address, value):
        self.u.mem_write(address, struct.pack('<I', value))

    def get(self, address):
        return struct.unpack('<I', self.u.mem_read(address, 4))[0]

    def cstring(self, address):
        result = bytearray()
        for i in range(256):
            b = self.u.mem_read(address + i, 1)[0]
            if b == 0:
                return result.decode()
            result.append(b)
        raise AssertionError('unterminated API path/name')

    def invoke(self, command, input_raw=None):
        arm = self.arm
        if input_raw is not None:
            self.input = input_raw
        self.output = None
        saved = {getattr(arm, 'UC_ARM_REG_R' + str(i)): 0xa1740000 + i * 0x1011 for i in range(4, 12)}
        for register, value in saved.items():
            self.u.reg_write(register, value)
        sp = 0x2001fff0
        for register, value in [(arm.UC_ARM_REG_R0, command), (arm.UC_ARM_REG_R1, self.api),
                (arm.UC_ARM_REG_R2, struct.unpack_from('<I', self.packed, 52)[0]),
                (arm.UC_ARM_REG_R3, self.packed[12]), (arm.UC_ARM_REG_SP, sp),
                (arm.UC_ARM_REG_LR, self.stop | 1), (arm.UC_ARM_REG_XPSR, 0x01000000),
                (arm.UC_ARM_REG_PRIMASK, 0), (arm.UC_ARM_REG_CONTROL, 0)]:
            self.u.reg_write(register, value)
        self.u.mem_write(sp, bytes(4))
        self.u.emu_start((self.base + self.entry) | 1, self.stop, count=220000000)
        assert self.u.reg_read(arm.UC_ARM_REG_PC) == self.stop, 'bounded APP did not return'
        assert self.u.reg_read(arm.UC_ARM_REG_SP) == sp
        assert all(self.u.reg_read(r) == v for r, v in saved.items()), 'AAPCS changed'
        assert self.u.reg_read(arm.UC_ARM_REG_PRIMASK) == self.u.reg_read(arm.UC_ARM_REG_CONTROL) == 0
        return self.u.reg_read(arm.UC_ARM_REG_R0)


def arm_checks(template, build, output):
    reader, reader_command = decoder(output)
    results, good = [], []
    for index, app in enumerate(build['apps']):
        base = [0x20004000, 0x20008000][index % 2]
        decoded_path = output / (app['mode'] + '.decoded')
        subprocess.run([str(reader), app['APP']['path'], str(decoded_path), hex(base)],
                       check=True, capture_output=True, timeout=20)
        decoded = decoded_path.read_bytes()
        machine = Machine(template, app, decoded, base)
        assert machine.invoke(0) == 0
        raw = request(template, 0)
        assert machine.invoke(1, raw) == 0 and machine.output is not None, app['mode']
        qualification = parse_report(machine.output, raw, template, app, decoded)
        assert qualification['rows'] == [] and qualification['header'][32:38] == CTX
        (output / (app['mode'] + '-qualify.bin')).write_bytes(machine.output)
        item = dict(mode=app['mode'], load_address=base, INIT=True, synthetic_qualification=True,
                    physical_speed_claim=False, decoded=pin(decoded_path))
        if app['mode'] in ('standalone-sram', 'shared-flash'):
            timed = request(template, 1, 115, CTX)
            before = sum(machine.target_calls.values())
            assert machine.invoke(1, timed) == 0
            parsed = parse_report(machine.output, timed, template, app, decoded)
            assert len(parsed['rows']) == 2
            assert all(x == 17 for row in parsed['rows'] for values in row['raw'] for x in values)
            assert machine.target_calls['real-runtime18-native'] > 0
            if app['shared_runtime']:
                assert machine.target_calls['public-strchr'] > 0
            (output / (app['mode'] + '-timed.bin')).write_bytes(machine.output)
            item['synthetic_raw_groups'] = 2 * FUNCTIONS
            item['synthetic_search_entries'] = sum(machine.target_calls.values()) - before
            good.append((app, decoded, base, timed, machine.output))
            # A cached duplicate must stop before searching or enabling DWT.
            before = sum(machine.target_calls.values())
            assert machine.invoke(1, timed) == 5
            assert struct.unpack_from('<I', machine.output, 8)[0] == 7
            assert sum(machine.target_calls.values()) == before
            item['cached_replay_rejected_before_search'] = True
        results.append(item)
        print(app['mode'], 'real packed ARM carrier PASS (synthetic ticks only)', flush=True)
    app, decoded, base, timed, good_raw = good[0]
    negative = 0
    # Checksums are repaired for semantic mutations so the parser must reach
    # the intended guard, rather than merely detect a corrupt byte stream.
    for word, value in [(7, 1), (11, 0), (13, 1), (14, 1), (16, 0), (20, 0),
                        (22, 1), (26, 0), (32, 0), (60, 0), (64, 0), (73, 0), (75, 0), (90, 0)]:
        changed = bytearray(good_raw)
        struct.pack_into('<I', changed, word * 4, value)
        struct.pack_into('<I', changed, 62 * 4, 0)
        struct.pack_into('<I', changed, 62 * 4, zlib.crc32(changed) & 0xffffffff)
        negative += rejects(lambda changed=changed: parse_report(changed, timed, template, app, decoded), 'semantic report mutation')
    for offset in [HEADER_WORDS * 4, HEADER_WORDS * 4 + 4, HEADER_WORDS * 4 + 8, HEADER_WORDS * 4 + 12]:
        changed = bytearray(good_raw);struct.pack_into('<I', changed, offset, 0)
        struct.pack_into('<I', changed, 62 * 4, 0)
        struct.pack_into('<I', changed, 62 * 4, zlib.crc32(changed) & 0xffffffff)
        negative += rejects(lambda changed=changed: parse_report(changed, timed, template, app, decoded), 'raw row mutation')
    for kind in ['wrong-nonce', 'stopped-DWT', 'stopped-both-clocks', 'changed-context', 'wrong-return']:
        machine = Machine(template, app, decoded, base)
        assert machine.invoke(0) == 0
        raw = timed
        if kind == 'wrong-nonce':
            raw = corrected_request(raw, **{'6': 1})
            expected = 1
        elif kind == 'stopped-DWT':
            machine.stopped_tick = True; expected = 5
        elif kind == 'stopped-both-clocks':
            machine.stopped_tick = machine.stopped_wall = True; expected = 5
        elif kind == 'changed-context':
            machine.change_context_on_target = True; expected = 2
        else:
            machine.corrupt_target_return = True; expected = 6
        assert machine.invoke(1, raw) == 5 and machine.output is not None, kind
        h = struct.unpack_from('<96I', machine.output)
        assert h[2] == expected and h[7] == 0, (kind, h[:10])
        if kind in ['wrong-nonce', 'stopped-DWT', 'stopped-both-clocks']:
            assert not machine.target_calls, kind
        assert machine.get(0xe0001000) == 0x40000000 and machine.get(0xe000edfc) == 0x800
        (output / ('negative-' + kind + '.bin')).write_bytes(machine.output)
        negative += 1
        print(kind, 'first fault retained, no later case ran', flush=True)
    return dict(APP_results=results, semantic_report_and_ARM_negative_guards=negative,
                production_decoder=pin(reader), decoder_command=reader_command,
                actual_device_timer=False, physical_IO=0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--host-only', action='store_true')
    a = p.parse_args()
    build = json.loads(a.build.read_text())
    template_path = Path(build['template']['path'])
    assert pin(template_path) == build['template']
    template = load_template(template_path)
    for app in build['apps']:
        assert pin(Path(app['APP']['path'])) == app['APP'] and pin(Path(app['ELF']['path'])) == app['ELF']
    a.output_dir.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    result = dict(status='PASS_HOST_OVERLAY_WIRE_ONLY', physical_IO=0, build=pin(a.build),
                  host_guards=host_guards(template), physical_speed_claim=False)
    if not a.host_only:
        result['ARM'] = arm_checks(template, build, a.output_dir)
        result['status'] = 'PASS_HOST_NEW_PACKED_CARRIERS_SYNTHETIC_TIME_ONLY'
    result['elapsed_HOST_seconds'] = time.monotonic() - start
    result['source_pins'] = [pin(HERE / x) for x in ['prepare.py', 'build.py', 'carrier.c', 'wire.py', 'model_test.py']]
    path = a.output_dir / 'RESULTS.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(result=pin(path), status=result['status'], physical_IO=0)))


if __name__ == '__main__':
    main()
