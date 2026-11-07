"""Numerical correctness of composition order and renamed tool observations."""
import itertools
import random
import unittest

from compose_common import make_task,rename_task,stack_depth
from emulator import Emulator
from harness import check_program
from tasks import value_of
from compose_round import container_path,REPO
from compose_balanced import wording_key


class CompositionTests(unittest.TestCase):
    def test_wording_dedup_preserves_aliasing_but_ignores_register_bijections(self):
        self.assertNotEqual(wording_key('Сложи R0 и R0.'),wording_key('Сложи R0 и R1.'))
        self.assertEqual(wording_key('Сложи R0 и R1.'),wording_key('Сложи R3 и R2.'))

    def test_host_checkpoint_path_is_relative_inside_docker(self):
        self.assertEqual(container_path(REPO/'.build/example/checkpoint'),'.build/example/checkpoint')
        self.assertEqual(container_path('.build/example/checkpoint'),'.build/example/checkpoint')

    def test_all_register_bijections_preserve_noncommutative_feedback(self):
        em=Emulator();task=make_task('Из R0 вычти произведение R1 и R2.',
          ['-','R0',['*','R1','R2']],random.Random(712),'rename',split='train',emulator=em)
        for permutation in itertools.permutations(['R0','R1','R2','R3']):
            changed=rename_task(task,permutation)
            self.assertTrue(check_program(em,changed['reference_code'],changed['public_tests']+changed['hidden_tests'])['pass'])
            self.assertEqual(changed['public_tests'][0]['expected_X'],task['public_tests'][0]['expected_X'])

    def test_three_operations_execute_without_losing_pending_left_argument(self):
        em=Emulator();expr=['-','R0',['/',['+','R1','R2'],'R3']]
        task=make_task('Остаток R0 после доли суммы R1 и R2 на R3.',expr,random.Random(713),'three',split='train',emulator=em)
        self.assertEqual(stack_depth(expr),3)
        self.assertTrue(check_program(em,task['reference_code'],task['public_tests']+task['hidden_tests'])['pass'])
        self.assertEqual(len(task['public_tests']+task['hidden_tests']),9)

    def test_degenerate_labels_do_not_enter_language_training(self):
        with self.assertRaises(ValueError):
            make_task('Разность R0 и R0.',['-','R0','R0'],random.Random(714),'degenerate',split='train')


if __name__=='__main__':unittest.main()
