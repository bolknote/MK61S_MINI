#!/usr/bin/env python3
"""Host-only checks for transport accounting and scheduling-model limits."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'offload', ROOT / 'tools/apps/mk61ai/model_m3_offload.py')
MODEL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODEL)


class OffloadModelTest(unittest.TestCase):
    def test_framed_bytes_at_write_chunk_boundary(self):
        self.assertEqual(MODEL.writes(252), (289, 1))
        self.assertEqual(MODEL.writes(253), (327, 2))
        # One Q4 row: 64 weight + 8 scale bytes. Legacy job has four RPCs.
        self.assertEqual(MODEL.job_wire(128, 1, 'stop_wait')[:2], (288, 4))
        self.assertEqual(MODEL.job_wire(128, 1, 'deferred')[:2], (186, 2))
        # Ten rows cross three WRITE chunks: 944 framed bytes, four RPCs.
        self.assertEqual(MODEL.job_wire(128, 10, 'deferred')[:2], (944, 4))
        self.assertEqual(MODEL.job_wire(384, 10, 'deferred')[:2], (2606, 10))

    def test_prefill_does_not_count_first_classifier(self):
        mats = [dict(rows=4, cols=32), dict(rows=4, cols=32)]
        document = dict(ok=True, actual_hz=270000000, config=dict(cores=2),
                        matching_checksums=True, results=[dict(
                            prefill_tokens=1, decode_tokens=1, decode_us=1000000,
                            matmul_us=300000)])
        _, profile = MODEL.baseline_profile(mats, document)
        self.assertEqual(profile['measured_workload_macs'], 384)
        self.assertAlmostEqual(profile['estimated_decode_linear_seconds'], 0.2)
        self.assertAlmostEqual(profile['estimated_decode_other_seconds'], 0.8)

    def test_equal_longest_local_core_has_no_free_speedup(self):
        mats = [dict(rows=128, cols=128)]
        args = ('pipelined', 1.0, 1e100, 0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(MODEL.forecast(mats, 32, 31, 1, *args)['estimated_seconds'], 1.0)
        self.assertAlmostEqual(MODEL.forecast(mats, 31, 31, 2, *args)['estimated_seconds'], 31/32)

    def test_selective_scheduler_keeps_baseline_when_uart_is_slow(self):
        mats = [dict(rows=128, cols=128), dict(rows=64, cols=128)]
        result = MODEL.selective_forecast(mats, 10, 1.0, 1.0, 1.0, 1.0, 16.0, 0.4)
        self.assertAlmostEqual(result['estimated_seconds'], 1.0)
        self.assertTrue(all(d['remote_rows'] == 0 for d in result['decisions']))

    def test_free_remote_work_cannot_remove_serial_fraction(self):
        mats = [dict(rows=128, cols=128)]
        result = MODEL.selective_forecast(mats, 10, 1.0, 1e100, 0.0, 0.0, 0.0, 0.4)
        self.assertAlmostEqual(result['estimated_seconds'], 0.6)
        self.assertEqual(result['decisions'][0]['remote_rows'], 128)


if __name__ == '__main__':
    unittest.main()
