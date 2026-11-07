import unittest
from full_isa_protocol import answer,decode,linear_instructions,prompt,REGISTERS


class FullIsaTests(unittest.TestCase):
    def test_every_byte_is_representable_without_an_arithmetic_ast(self):
        for opcode in range(256):self.assertEqual(decode(answer([opcode])),[opcode])

    def test_jump_addresses_are_not_counted_as_operations(self):
        rows=linear_instructions([0x51,0x1C,0x60,0x50])
        self.assertEqual([r['opcode']for r in rows],[0x51,0x60,0x50])
        self.assertEqual(rows[0]['operand'],0x1C)
        with self.assertRaises(ValueError):linear_instructions([0x53])

    def test_full_register_and_angle_contract(self):
        self.assertEqual(len(REGISTERS),15);self.assertEqual(REGISTERS[-1],'RE')
        for mode in ['RAD','DEG','GRAD']:self.assertIn(mode,prompt('Синус 22.',angle=mode))
        self.assertNotIn('<calc>',answer([2,2,0x1C,0x50]))
        with self.assertRaises(ValueError):prompt('Синус 22.',angle='unknown')


if __name__=='__main__':unittest.main()
