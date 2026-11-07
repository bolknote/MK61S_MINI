import math
import unittest

from full_isa_math import compile_expr
from full_isa_vm import FullVM


class FullCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.vm=FullVM()

    def test_literal_sine_in_all_angle_modes(self):
        for mode,angle in [('RAD',22),('DEG',math.radians(22)),('GRAD',22*math.pi/200)]:
            state,_=self.vm.execute(compile_expr(['sin',{'constant':22}])+[0x50],{},angle=mode)
            self.assertEqual(state['status'],'stopped');self.assertAlmostEqual(float(state['numeric']['X']),math.sin(angle),delta=2e-6)

    def test_power_retains_correct_enclosing_expression(self):
        expr=['+',['pow','R0','R1'],'RE']
        state,_=self.vm.execute(compile_expr(expr)+[0x50],{'R0':2,'R1':3,'RE':5})
        self.assertAlmostEqual(float(state['numeric']['X']),13,delta=3e-5)
        self.assertEqual(state['numeric']['RE'],'5')

    def test_nondecimal_logical_result_is_preserved(self):
        state,context=self.vm.execute([0x38,0x50],{'X':'8.7','Y':'8.8'})
        self.assertIn('F',state['raw']['X']);self.assertIsNone(state['numeric']['X'])
        self.vm.restore(context);self.assertEqual(self.vm.save(),context)

    def test_domain_error_is_observable(self):
        state,_=self.vm.execute([0x21,0x50],{'X':-1})
        self.assertEqual(state['status'],'error')

    def test_resume_keeps_the_game_score(self):
        program=[0x0D,0x44,0x50,0x64,0x10,0x44,0x50,0x51,0x03]
        state,context=self.vm.execute(program,{'X':77,'R4':99})
        self.assertEqual(state['numeric']['R4'],'0')
        total=0
        for delta in [5,-3,8]:
            state,context=self.vm.execute(None,{'X':delta},context=context);total+=delta
            self.assertEqual(float(state['numeric']['X']),total);self.assertEqual(float(state['numeric']['R4']),total)

    def test_all_four_loop_counters(self):
        for counter,op in [(0,0x5D),(1,0x5B),(2,0x58),(3,0x5A)]:
            state,_=self.vm.execute([op,0x00,0x50],{f'R{counter}':5})
            self.assertEqual(state['status'],'stopped');self.assertEqual(state['numeric'][f'R{counter}'],'1')


if __name__=='__main__':unittest.main()
