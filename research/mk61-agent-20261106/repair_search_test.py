"""Verify public-only repair, hidden grading, unsupported effects and hard budgets."""
import unittest

from emulator import Emulator
from evaluate_repairs import repair_result
from harness import check_program
from repair_search import search


class RepairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.em=Emulator()

    def test_real_emulator_repairs_wrong_operator(self):
        public=[{'registers':{'R0':3,'R1':5},'expected_X':'8'},
                {'registers':{'R0':7,'R1':2},'expected_X':'9'}]
        result=search(self.em,[0x60,0x61,0x11,0x50],public,budget=32)
        self.assertTrue(result['found']);self.assertLessEqual(result['trials'],32)
        self.assertTrue(check_program(self.em,result['code'],[{'registers':{'R0':-8,'R1':4},'expected_X':'-4'}])['pass'])

    def test_hidden_failure_does_not_trigger_search(self):
        source={'id':'hidden','kind':'test','pass':False,'public_pass':True,'code':[0x60,0x50]}
        task={'public_tests':[{'registers':{'R0':1},'expected_X':'1'}],
              'hidden_tests':[{'registers':{'R0':-2},'expected_X':'2'}]}
        result=repair_result(source,task,self.em)
        self.assertFalse(result['hybrid_pass']);self.assertNotIn('repair',result)

    def test_first_public_fitting_candidate_can_fail_hidden_and_stops(self):
        # Public R0=1 cannot distinguish abs(R0) from identity. The first
        # repair is abs; hidden negative input must FAIL, not guide more search.
        source={'id':'ambiguity','kind':'test','pass':False,'public_pass':False,'code':[0x60,0x0B,0x50]}
        task={'public_tests':[{'registers':{'R0':1},'expected_X':'1'}],
              'hidden_tests':[{'registers':{'R0':-2},'expected_X':'-2'}]}
        result=repair_result(source,task,self.em)
        self.assertTrue(result['repair']['found']);self.assertFalse(result['hybrid_pass'])

    def test_memory_side_effects_are_not_silently_ignored(self):
        case={'registers':{'R0':5},'expected_X':'5','expected_registers':{'R4':'5'}}
        result=search(self.em,[0x60,0x50],[case])
        self.assertFalse(result['found']);self.assertEqual(result['trials'],0)

    def test_budget_is_hard(self):
        result=search(self.em,[0x60,0x61,0x10,0x50],[{'registers':{'R0':3,'R1':5},'expected_X':'15'}],budget=1)
        self.assertFalse(result['found']);self.assertEqual(result['trials'],1)


if __name__=='__main__':unittest.main()
