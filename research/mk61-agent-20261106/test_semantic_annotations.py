import unittest

from semantic_teacher import annotation,jobs,teacher_prefix
from semantic_common import auxiliary_answer


class AnnotationTests(unittest.TestCase):
    def test_teacher_functional_notation_is_normalized_without_changing_order(self):
        expr=['-','R2',['+','R3',['/','R1','R0']]]
        self.assertEqual(teacher_prefix('-(R2,+(R3,/(R1,R0)))'),expr)
        self.assertEqual(teacher_prefix('- R2 + R3 / R1 R0'),expr)
        self.assertEqual(teacher_prefix('-(R2,(+ R3 (/ R1 R0)))'),expr)
        self.assertEqual(teacher_prefix('-R2+R3/R1R0'),expr)
        for wrong in ['R0-R1','abs(R0,R1)','sin(R0)','abs(R0))','__import__(R0)']:
            with self.assertRaises(ValueError):teacher_prefix(wrong)
    def test_noncommutative_steps_reconstruct_the_whole_expression(self):
        expr=['/',['-','R2','R0'],'R1'];roles={'R0':'расход','R1':'число групп','R2':'запас'}
        roles,steps=annotation(expr,roles,[{'op':'-','args':['R2','R0']},{'op':'/','args':['t1','R1']}])
        text=auxiliary_answer({'expression':expr,'roles':roles,'steps':steps})
        self.assertIn('Из R2 вычесть R0',text);self.assertIn('Разделить t1 на R1',text)

    def test_swapped_operands_or_forward_reference_are_rejected(self):
        expr=['/',['-','R2','R0'],'R1'];roles={'R0':'расход','R1':'число групп','R2':'запас'}
        for steps in [[{'op':'-','args':['R0','R2']},{'op':'/','args':['t1','R1']}],
                      [{'op':'-','args':['R2','t2']},{'op':'/','args':['R0','R1']}]]:
            with self.assertRaises(ValueError):annotation(expr,roles,steps)

    def test_missing_input_role_is_rejected(self):
        with self.assertRaises(ValueError):annotation(['-','R0','R1'],{'R0':'запас'},[{'op':'-','args':['R0','R1']}])

    def test_whole_source_documents_and_scenario_pairs_are_partitioned(self):
        rows=jobs();train=[r for r in rows if r['split']=='train'];val=[r for r in rows if r['split']=='validation']
        self.assertFalse({r['source_id']for r in train}&{r['source_id']for r in val})
        self.assertFalse({r['language_family']for r in train}&{r['language_family']for r in val})
        self.assertEqual(len(rows),1120)


if __name__=='__main__':unittest.main()
