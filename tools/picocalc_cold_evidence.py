#!/usr/bin/env python3
"""Interpret saved PicoCalc cold-start evidence without accessing a device.

Use only the first observed status after power-on. A later healthy status can
hide an early fault/restart. This tool reports evidence; it does not accept a
firmware release or establish why RAM was corrupted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


def field(text, name):
    values = re.findall(r'\b' + re.escape(name) + r'=([^\s]+)', text)
    if len(values) > 1:
        raise ValueError('Repeated evidence field: ' + name)
    return values[0] if values else None


def classify(status, crash, build):
    if not re.fullmatch(r'[0-9a-fA-F]{8}', build):
        raise ValueError('Expected an eight-digit firmware build ID')
    if field(status, 'BUILD') != build.upper():
        raise ValueError('Status does not identify the requested firmware build')
    reset, boots, rtc = (field(status, name) for name in ('RESET_REASON', 'BOOTS', 'RTC_SET'))
    crash_state = field(status, 'CRASH')
    previous_valid = field(status, 'PREVIOUS_VALID')
    record_build = field(crash, 'BUILD')
    record_current = field(crash, 'CURRENT_BUILD')
    record_crc = field(crash, 'CRC')
    record_reset = field(crash, 'RESET_AT_FAULT')
    record_present = any(value is not None for value in (record_build, record_crc, record_reset))
    reply_none = field(crash, 'CRASH') == 'NONE' and not record_present
    conflict = crash_state == 'NONE' and bool(crash.strip()) and not reply_none
    record_valid = (crash_state == 'AVAILABLE' and record_crc == 'OK'
                    and record_build == build.upper()
                    and record_current in (None, build.upper()))
    cold_fault = record_valid and record_reset == '00010000' and rtc == '0'
    first = (reset == '00010000' and boots == '1' and rtc == '0'
             and crash_state == 'NONE' and not conflict)
    early = (reset == '00010001' and boots == '1' and rtc == '0'
             and previous_valid == '0' and crash_state != 'AVAILABLE')
    if cold_fault:
        classification = 'COLD_FAULT_FOLLOWED_BY_RESET'
    elif first:
        classification = 'FIRST_BOOT_WITH_COLD_RESET_EVIDENCE'
    elif early:
        classification = 'POSSIBLE_EARLY_RESET_RECORD_LOST'
    elif rtc == '1':
        classification = 'RTC_RETAINED_OR_CAPTURED_AFTER_RESTORATION'
    else:
        classification = 'INSUFFICIENT_COLD_RESET_EVIDENCE'
    return dict(classification=classification, true_cold_evidence=bool(cold_fault or first),
                first_boot_without_reported_fault=first,
                possible_early_reset_record_lost=early,
                current_image_fault_record_valid=record_valid,
                status_crash_reply_conflict=conflict,
                reset_reason=reset, boots=boots, rtc_set=rtc, crash_state=crash_state,
                limit='Use the first observed status only. An early fault before diagnostics initialization '
                      'may lose its record. No reported fault does not prove intact RAM.')


def trace_evidence(words):
    if len(words) != 45 or any(not isinstance(n, int) or not 0 <= n <= 0xFFFFFFFF for n in words):
        raise ValueError('Expected exactly 45 unsigned 32-bit trace words')
    if words[0] != 0xC01D7432 or words[1] != 0x3FE28BCD or words[2] > 8:
        return dict(valid=False, complete_first_startup=False)
    points = [dict(zip(('phase', 'bad', 'address', 'expected', 'actual'), words[5+i*5:10+i*5]))
              for i in range(words[2])]
    complete = len(points) == 8 and [p['phase'] for p in points] == list(range(8))
    return dict(valid=True, complete_first_startup=complete, points=points,
                all_eight_points_clean=complete and all(p['bad'] == 0 for p in points),
                veneer=f'{words[3]:08X}', software_guard_path=words[4],
                limit='The software guard flag does not establish MPU CTRL. Repeated or missing '
                      'phases cannot prove a complete first startup; only the scanned RAM is covered.')


def reader_records(transcript, canonical):
    if not canonical.startswith('/') or any(c in canonical for c in '\r\n"'):
        raise ValueError('Expected the absolute path used to open COLDREAD.APP')
    expected = {('MPU', 0xE000ED90): 20}
    expected.update({('TRACE', 0x200000C0+i): 20 for i in range(0, 180, 20)})
    expected.update({('RAM', base+i): 32 for base in (0x20005FC0, 0x200062C0) for i in range(0, 128, 32)})
    observed = {}
    for line in transcript.splitlines():
        if not line.strip() or line in ('mk61>', 'mk61> ', 'APP_FLOW_RESULT=0', 'open "' + canonical + '"'):
            continue
        if re.fullmatch(r'APP_RESULT=0 CRC=[0-9A-F]{8} MEMORY=612', line):
            continue
        match = re.fullmatch(r'(MPU|TRACE|RAM) ([0-9A-F]{8}) ([0-9A-F]+)', line)
        if not match:
            raise ValueError('Unknown reader output: ' + line)
        key = (match[1], int(match[2], 16))
        if key not in expected or key in observed:
            raise ValueError('Unknown or duplicate reader record: ' + str(key))
        data = bytes.fromhex(match[3])
        if len(data) != expected[key]:
            raise ValueError('Wrong reader record width: ' + str(key))
        observed[key] = data
    if set(observed) != set(expected):
        raise ValueError('Missing reader records: ' + str(sorted(set(expected) - set(observed))))
    return observed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', type=Path, required=True, help='First observed status, before restoration')
    parser.add_argument('--crash', type=Path, help='Saved crash show response, if available')
    parser.add_argument('--build', required=True, help='Exact eight-digit firmware build ID')
    parser.add_argument('--reader', type=Path, help='Saved transcript of the 624-byte COLDREAD.APP')
    parser.add_argument('--reader-path', help='Exact absolute APP path echoed in that transcript')
    parser.add_argument('--require-first-boot', action='store_true',
                        help='Exit 1 unless evidence identifies a first cold boot without a reported fault')
    args = parser.parse_args(argv)
    if bool(args.reader) != bool(args.reader_path):
        parser.error('--reader and --reader-path must be supplied together')
    sources = {}

    def read(name, path):
        raw = path.read_bytes()
        sources[name] = dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())
        return raw.decode('ascii')

    try:
        report = classify(read('status', args.status), read('crash', args.crash) if args.crash else '', args.build)
        if args.reader:
            records = reader_records(read('reader', args.reader), args.reader_path)
            mpu = struct.unpack('<5I', records['MPU', 0xE000ED90])
            report['mpu'] = dict(zip(('type', 'ctrl', 'rnr', 'rbar', 'rasr'), mpu))
            trace = b''.join(records['TRACE', 0x200000C0+i] for i in range(0, 180, 20))
            report['trace'] = trace_evidence(struct.unpack('<45I', trace))
            report['memory_reads'] = {f'{label}:{address:08X}': data.hex()
                                      for (label, address), data in records.items() if label == 'RAM'}
        report.update(sources=sources, hardware_access=False, production_acceptance=False)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(args.require_first_boot and not report['first_boot_without_reported_fault'])


if __name__ == '__main__':
    raise SystemExit(main())
