import unittest
from ha_protocol import *
from full_isa_math import compile_expr


class ProtocolTest(unittest.TestCase):
    def test_pool_is_lexical(self):
        self.assertEqual(constants('МК-61: sin(-.125)+R0+22; L3; .125; -0.0'),['0','1','-1','-0.125','22','0.125'])

    def test_every_byte_survives(self):
        for byte in range(256):
            code=[byte,0x50];body=encode(code,['0','1','-1'],'asm')
            self.assertEqual(assemble(body,['0','1','-1'],'asm'),code)

    def test_literals_and_signs(self):
        for number in ['.125','-.875','22','100','-17','0','-0.0','12.75']:
            pool=constants('Число '+number)
            code=compile_expr(['neg',{'constant':number}])+[0x50]
            self.assertEqual(assemble(encode(code,pool,'asm'),pool,'asm'),code)

    def test_labels_in_bcd(self):
        body=[0x51,0xFF,3,7]+[0x54]*8+[0xFF,2,7,0x02,0x50]
        self.assertEqual(assemble(body,[],'asm'),[0x51,0x10]+[0x54]*8+[0x02,0x50])
        for cell in range(105):self.assertEqual(unaddress(address(cell)),cell)

    def test_suffix_insert_delete(self):
        for current,wanted in [([1,2,3],[1,7,8,9]),([1,2,3],[1]),([1],[1,2]),([1],[7])]:
            kind,body=parse_call(patch_call(current,wanted),current)
            self.assertEqual(kind,'patch');self.assertEqual(body,wanted)

    def test_bad_directives_and_bounds(self):
        for body in [[0xFF],[0xFF,1],[0xFF,1,99],[0xFF,3,1],[0xFF,7,0],[0]*106]:
            with self.assertRaises(ValueError):assemble(body,['0'],'asm')


if __name__=='__main__':unittest.main()
