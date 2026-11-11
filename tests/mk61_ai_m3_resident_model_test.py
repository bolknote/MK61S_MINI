#!/usr/bin/env python3
"""Memory ownership, serial framing and resident-weight model bounds."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/apps/mk61ai'))
import model_m3_resident_weights as model


class ResidentModelTest(unittest.TestCase):
    def setUp(self):
        self.firmware=dict(global_ram_bytes=9716,stack_reserved_bytes=4096,
            ram_unallocated_bytes=6668,image_bytes=26664,
            flash=dict(page_bytes=1024,start='0x08000000',
                       preserved_settings=['0x0800f800','0x08010000']))
        self.module=dict(memory_limit=6144,memory_bytes=2916)
        self.head=dict(rows=8192,cols=128,bytes_per_row=72)
        self.result=dict(baseline_seconds=1.114016,assumed_parallel_fraction=0.37205165814494595,
            linear_macs_per_decode=3014656,wire_bytes_per_second=225000,
            calibrated_job_residual_us_per_request=285.3175675675676)

    def test_arena_not_double_counted_and_settings_pages_preserved(self):
        b=model.cache_budgets(self.firmware,self.module)
        self.assertEqual(b['current_slot_weight_budget'],2716)
        self.assertEqual(b['expanded_slot_weight_budget'],7336)
        self.assertEqual(b['flash_page_aligned_free_bytes'],35*1024)
        self.assertEqual(b['flash_pages_left_for_firmware_growth'],3*1024)
        self.assertEqual(b['flash_weight_budget'],32704)
        self.assertEqual(model.cache_budgets(self.firmware,self.module,module_growth=10000)
                         ['expanded_slot_weight_budget'],0)

    def test_flash_cache_cannot_overlap_settings(self):
        with self.assertRaises(ValueError):
            model.cache_budgets(self.firmware,self.module,flash_cache_bytes=36*1024)

    def test_result_frame_limit_and_vector_sent_only_once(self):
        # 61 floats fill the 244-byte START_RESULT data allowance.
        a=model.resident_wire(128,61,'logits')
        b=model.resident_wire(128,62,'logits')
        self.assertEqual((a['bytes'],a['rpcs'],a['jobs']),(498,2,1))
        self.assertEqual((b['bytes'],b['rpcs'],b['jobs']),(612,4,2))
        self.assertEqual(b['activation_bytes'],144)
        self.assertEqual(model.resident_wire(128,454,'argmax')['bytes'],262)

    def test_full_classifier_results_fit_and_reach_memory_bound(self):
        s=model.resident_case('flash',[32704],self.head,self.result)
        self.assertEqual(s['cached_rows'],454)
        self.assertLessEqual(s['cached_weights_and_scales_bytes'],32704)
        self.assertEqual(s['local_core0_rows']+s['local_core1_rows']+s['cached_rows'],8192)
        expected=self.result['baseline_seconds']*self.result['assumed_parallel_fraction']*32688/1695744
        self.assertAlmostEqual(s['predictions'][0]['time_saved_ms']/1000,expected)
        self.assertTrue(s['predictions'][0]['fully_hidden'])

    def test_service_gaps_can_destroy_predicted_gain(self):
        s=model.resident_case('flash',[32704],self.head,self.result,scheduler_gap_us=64)
        self.assertFalse(s['predictions'][0]['fully_hidden'])
        self.assertGreater(s['predictions'][0]['token_seconds'],self.result['baseline_seconds'])

    def test_zero_storage_cannot_speed_up_inference(self):
        s=model.resident_case('none',[0],self.head,self.result)
        self.assertAlmostEqual(s['predictions'][0]['token_seconds'],self.result['baseline_seconds'])
        self.assertEqual(s['predictions'][0]['traffic']['bytes'],0)


if __name__=='__main__':
    unittest.main()
