#!/usr/bin/env python3
"""Offline regression checks for PicoCalc first-observed cold-start evidence."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / 'tools/picocalc_cold_evidence.py'
spec = importlib.util.spec_from_file_location('picocalc_cold_evidence', TOOL)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)
BASE = 'BUILD=0FB4229F RESET_REASON=00010000 BOOTS=1 RTC_SET=0 PREVIOUS_VALID=0 '


def trace(phases=range(8)):
    phases = list(phases)
    words = [0xC01D7432, 0x3FE28BCD, len(phases), 0x200062E8, 1] + [0] * 40
    for i, phase in enumerate(phases):
        words[5+i*5] = phase
    return words


def reader():
    lines = ['open "/PCLD-007/COLDREAD.app"', 'MPU E000ED90 ' + struct.pack('<5I', 8, 0, 0, 0, 0).hex().upper()]
    raw = struct.pack('<45I', *trace())
    lines += [f'TRACE {0x200000C0+i:08X} ' + raw[i:i+20].hex().upper() for i in range(0, 180, 20)]
    lines += [f'RAM {base+i:08X} ' + 'AB' * 32
              for base in (0x20005FC0, 0x200062C0) for i in range(0, 128, 32)]
    return lines + ['APP_RESULT=0 CRC=01234567 MEMORY=612', 'APP_FLOW_RESULT=0', 'mk61> ']


class ColdEvidenceTest(unittest.TestCase):
    def classify(self, status, crash='CRASH=NONE'):
        return evidence.classify(status, crash, '0fb4229f')

    def test_explicit_no_crash_is_required(self):
        clean = self.classify(BASE + 'CRASH=NONE')
        self.assertTrue(clean['first_boot_without_reported_fault'])
        for marker in ('', 'CRASH=UNKNOWN', 'CRASH=AVAILABLE', 'CRASH=none'):
            with self.subTest(marker=marker):
                result = self.classify(BASE + marker)
                self.assertFalse(result['true_cold_evidence'])
                self.assertFalse(result['first_boot_without_reported_fault'])
                self.assertEqual(result['classification'], 'INSUFFICIENT_COLD_RESET_EVIDENCE')

    def test_first_boot_requires_reset_boot_count_and_lost_rtc(self):
        for old, new in (('00010000', '00010001'), ('BOOTS=1', 'BOOTS=2'), ('RTC_SET=0', 'RTC_SET=1')):
            with self.subTest(new=new):
                self.assertFalse(self.classify((BASE + 'CRASH=NONE').replace(old, new))['true_cold_evidence'])

    def test_early_reset_record_loss_is_not_clean(self):
        status = BASE.replace('00010000', '00010001')
        for marker in ('', 'CRASH=NONE', 'CRASH=UNKNOWN'):
            result = self.classify(status + marker)
            self.assertEqual(result['classification'], 'POSSIBLE_EARLY_RESET_RECORD_LOST')
            self.assertFalse(result['true_cold_evidence'])
            self.assertFalse(result['first_boot_without_reported_fault'])

    def test_fault_must_match_exact_image_crc_and_original_reset(self):
        status = BASE.replace('00010000', '00010001').replace('BOOTS=1', 'BOOTS=2') + 'CRASH=AVAILABLE'
        crash = 'BUILD=0FB4229F CURRENT_BUILD=0FB4229F CRC=OK RESET_AT_FAULT=00010000'
        good = self.classify(status, crash)
        self.assertTrue(good['true_cold_evidence'])
        self.assertFalse(good['first_boot_without_reported_fault'])
        self.assertEqual(good['classification'], 'COLD_FAULT_FOLLOWED_BY_RESET')
        for bad in (crash.replace('BUILD=0FB4229F ', 'BUILD=1C818050 ', 1),
                    crash.replace('CURRENT_BUILD=0FB4229F', 'CURRENT_BUILD=1C818050'),
                    crash.replace('CRC=OK', 'CRC=BAD'), crash.replace('00010000', '00010001'), ''):
            self.assertFalse(self.classify(status, bad)['true_cold_evidence'])

    def test_conflicting_or_unknown_crash_reply_cannot_make_a_clean_capture(self):
        for crash in ('CRASH=UNKNOWN', 'ERROR cannot read crash',
                      'BUILD=0FB4229F CRC=OK RESET_AT_FAULT=00010000',
                      'CRASH=NONE BUILD=0FB4229F CRC=OK'):
            with self.subTest(crash=crash):
                result = self.classify(BASE + 'CRASH=NONE', crash)
                self.assertTrue(result['status_crash_reply_conflict'])
                self.assertFalse(result['first_boot_without_reported_fault'])
                self.assertFalse(result['true_cold_evidence'])
        with self.assertRaises(ValueError):
            self.classify(BASE + 'CRASH=NONE', 'CRASH=NONE CRC=OK CRC=BAD')

    def test_retained_rtc_does_not_prove_power_was_removed(self):
        result = self.classify(BASE.replace('RTC_SET=0', 'RTC_SET=1') + 'CRASH=NONE')
        self.assertEqual(result['classification'], 'RTC_RETAINED_OR_CAPTURED_AFTER_RESTORATION')
        self.assertFalse(result['true_cold_evidence'])

    def test_missing_fields_never_prove_a_clean_start(self):
        for name in ('RESET_REASON=00010000', 'BOOTS=1', 'RTC_SET=0'):
            self.assertFalse(self.classify(BASE.replace(name, '') + 'CRASH=NONE')['true_cold_evidence'])

    def test_multiple_statuses_or_wrong_build_are_rejected(self):
        for extra in ('RESET_REASON=00010000', 'BOOTS=1', 'RTC_SET=0', 'CRASH=NONE', 'BUILD=0FB4229F'):
            with self.assertRaises(ValueError):
                self.classify(BASE + 'CRASH=NONE ' + extra)
        for build in ('bad', '0FB4229G', 'A7483AE6'):
            with self.assertRaises(ValueError):
                evidence.classify(BASE + 'CRASH=NONE', '', build)

    def test_trace_needs_all_ordered_phases(self):
        self.assertTrue(evidence.trace_evidence(trace())['all_eight_points_clean'])
        for phases in ([], [0, 1], [0, 1, 2, 3, 4, 5, 0, 1], [1, 2, 3, 4, 5, 6, 7, 0]):
            result = evidence.trace_evidence(trace(phases))
            self.assertTrue(result['valid'])
            self.assertFalse(result['complete_first_startup'])
            self.assertFalse(result['all_eight_points_clean'])

    def test_trace_reports_corruption_without_equating_guard_to_mpu(self):
        words = trace()
        words[6] = 3
        result = evidence.trace_evidence(words)
        self.assertTrue(result['complete_first_startup'])
        self.assertFalse(result['all_eight_points_clean'])
        self.assertEqual(result['software_guard_path'], 1)
        self.assertNotIn('mpu_enabled', result)

    def test_bad_trace_metadata_and_sizes(self):
        for index, value in ((0, 0), (1, 0), (2, 9)):
            words = trace()
            words[index] = value
            self.assertFalse(evidence.trace_evidence(words)['valid'])
        for words in (trace()[:-1], trace() + [0], [-1] + trace()[1:]):
            with self.assertRaises(ValueError):
                evidence.trace_evidence(words)

    def test_reader_exact_schema_and_widths(self):
        records = evidence.reader_records('\r\n'.join(reader()), '/PCLD-007/COLDREAD.app')
        self.assertEqual(len(records), 18)
        self.assertEqual(len(records['MPU', 0xE000ED90]), 20)
        self.assertEqual(len(records['RAM', 0x20005FC0]), 32)

    def test_reader_rejects_partial_duplicate_unknown_short_and_error(self):
        valid = reader()
        bad_cases = [valid[:2] + valid[3:], valid + [valid[1]],
                     valid + ['RAM 20010000 ' + 'AB' * 32], valid + ['ERROR cannot read'],
                     [line[:-2] if line.startswith('MPU ') else line for line in valid],
                     [line.replace('APP_FLOW_RESULT=0', 'APP_FLOW_RESULT=1') for line in valid]]
        for lines in bad_cases:
            with self.assertRaises(ValueError):
                evidence.reader_records('\n'.join(lines), '/PCLD-007/COLDREAD.app')

    def test_cli_provenance_and_admission_under_python_optimization(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'first.txt'
            for marker, expected in (('CRASH=NONE', 0), ('CRASH=UNKNOWN', 1), ('', 1)):
                path.write_text(BASE + marker)
                for optimization in ([], ['-O']):
                    result = subprocess.run([sys.executable, *optimization, str(TOOL), '--status', str(path),
                                             '--build', '0FB4229F', '--require-first-boot'],
                                            text=True, capture_output=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report['first_boot_without_reported_fault'], expected == 0)
                    self.assertFalse(report['hardware_access'])
                    self.assertFalse(report['production_acceptance'])
                    self.assertEqual(len(report['sources']['status']['sha256']), 64)

    def test_cli_combines_reader_without_claiming_mpu_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / 'status.txt').write_text(BASE + 'CRASH=NONE')
            (d / 'reader.txt').write_text('\n'.join(reader()))
            result = subprocess.run([sys.executable, str(TOOL), '--status', str(d / 'status.txt'),
                                     '--build', '0FB4229F', '--reader', str(d / 'reader.txt'),
                                     '--reader-path', '/PCLD-007/COLDREAD.app'], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['mpu']['ctrl'], 0)
            self.assertEqual(report['trace']['software_guard_path'], 1)
            self.assertTrue(report['trace']['all_eight_points_clean'])
            self.assertFalse(report['production_acceptance'])


if __name__ == '__main__':
    unittest.main()
