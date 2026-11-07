import re
import unittest

from compose_morphology import variants,equivalent


class RussianGrammar(unittest.TestCase):
    def test_case_variants_keep_actual_register_names(self):
        expr=['/',['+','R0','R1'],['-','R2','R3']]
        for text in variants(expr):
            self.assertEqual(set(re.findall(r'R[0-3]',text)),{'R0','R1','R2','R3'})
            self.assertFalse(re.search(r'\br[0-3]\b',text))

    def test_inverse_accepts_equivalence_and_rejects_reversed_subtraction(self):
        self.assertTrue(equivalent(['square','R0'],['*','R0','R0']))
        self.assertFalse(equivalent(['-','R0',['*','R1','R2']],['-',['*','R1','R2'],'R0']))
        self.assertFalse(equivalent(['square','R0'],['square','R1']))


if __name__=='__main__':unittest.main()
