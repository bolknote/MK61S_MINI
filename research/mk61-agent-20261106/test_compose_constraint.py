import unittest

from compose_constraint import Grammar,State


class GrammarTests(unittest.TestCase):
    def test_all_four_inputs_and_three_operations(self):
        g=Grammar(['R0','R1','R2','R3'])
        state=g.advance(State(),'<calc>+ + * R0 R1 R2 R3</calc><write>')
        self.assertIsNotNone(state)
        self.assertEqual(state.phase,'done')
        self.assertIsNone(g.advance(State(),'<calc>+ * R0 R1 R2</calc>'))
        self.assertIsNone(g.advance(State(),'<calc>a'))

    def test_partial_bpe_chunks_and_budget(self):
        g=Grammar(['R0','R1'])
        state=State()
        for chunk in ['<','calc','>+',' abs R','0 R','1</ca','lc>']:state=g.advance(state,chunk)
        self.assertEqual(state.phase,'done')
        self.assertIsNone(g.advance(State(),'<calc>abs abs abs abs'))
        self.assertIsNone(g.advance(State(),'<calc>abs abs + a'))
        self.assertIsNone(g.advance(State(),'<calc>+ R0 R3'))

    def test_does_not_choose_the_operations(self):
        g=Grammar(['R0','R1'])
        for op in ['+','-','*','/']:
            self.assertEqual(g.advance(State(),'<calc>'+op+' R1 R0</calc>').phase,'done')
        self.assertIsNone(g.advance(State(),'<calc>R0</calc>'))


if __name__=='__main__':unittest.main()
