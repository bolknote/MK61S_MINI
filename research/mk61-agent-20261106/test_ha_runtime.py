import json
import unittest
from ha_protocol import encode,constants,write_call
from ha_runtime import Session
from full_isa_prepare import make_task
from full_isa_vm import FullVM


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.task=make_task(FullVM(),[0x60,0x61,0x10,0x50],'Сумму R0 и R1 выдай в X.','unit','sum','train','RAD',
          [{'R0':'2','R1':'3','X':'0'},{'R0':'5','R1':'7','X':'1'},{'R0':'11','R1':'13','X':'2'}],check_names=['X'])

    def test_no_expected_or_judgment_in_feedback(self):
        s=Session(self.task,'direct',[0x60,0x61,0x11,0x50]);s.run(0)
        value=json.loads(s.observation)
        self.assertNotIn('expected',s.observation);self.assertNotIn('PASS',s.observation);self.assertNotIn('FAIL',s.observation)
        self.assertEqual(value['actual'][0]['X'],'-1.0000000 00')
        self.assertNotIn('events',s.observation)
        self.assertEqual(s.apply('<trace/>'),'trace');self.assertIn('events',s.observation)
        self.assertEqual(s.apply('<patch>00 02 10 50</patch><run/>'),'patch')
        self.assertEqual(s.body,[0x60,0x61,0x10,0x50])
        self.assertEqual(s.apply('<run>01</run>'),'run')
        self.assertEqual(s.apply('<done/>'),'done');self.assertTrue(s.finished)

    def test_hidden_inputs_are_unavailable(self):
        s=Session(self.task,'direct',[0x50])
        self.assertEqual(s.apply('<run>02</run>'),'error')
        self.assertEqual(s.observation,'ERROR CASE_UNAVAILABLE')


if __name__=='__main__':unittest.main()
