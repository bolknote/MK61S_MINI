"""Checks for failure modes that could invalidate the experiment's conclusion."""
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import torch
import torch.nn.functional as F
from transformers import AutoModelForCausalLM,AutoTokenizer

from capacity_train import example_loss,renamed
from course_common import parse_prefix,prefix,canonical,make_task
from course_eval import parsing,grading_tasks
from emulator import Emulator
from harness import check_program
from lowbit import FORMATS,attach,export,load,pack_codes,unpack_codes,quantize
from tasks import BUILD,compile_expr
from train import plain_copy


class CapacityChecks(unittest.TestCase):
    def test_semantic_grading_accepts_equivalent_square_without_oracle(self):
        task=make_task('Найди квадрат R1.',['square','R1'],random.Random(14),'unit-square',level=1,split='unit')
        model=torch.nn.Linear(1,1)
        with patch('course_eval.generate_many',return_value=['<calc>* R1 R1</calc>'])as generate:
            result=parsing(model,None,[task])
        self.assertTrue(result['details'][0]['pass'])
        self.assertFalse(result['details'][0]['exact_ast'])
        self.assertNotIn('expected_X',str(generate.call_args))
        self.assertNotIn('Проверки:',str(generate.call_args))

    def test_unused_registers_and_read_only_invariants_are_exercised(self):
        task=make_task('Вычти R1 из R0.',['-','R0','R1'],random.Random(15),'unit-difference',level=1,split='unit')
        checked=grading_tasks([task])[0]
        for case in checked['public_tests']+checked['hidden_tests']:
            self.assertEqual(set(case['registers']),{'R0','R1','R2','R3'})
            self.assertEqual(case['registers'],case['expected_registers'])
        em=Emulator()
        self.assertTrue(check_program(em,checked['reference_code'],checked['public_tests']+checked['hidden_tests'])['pass'])

    def test_prefix_is_a_safe_bounded_grammar(self):
        value=['-','R2',['*','R0','R1']]
        self.assertEqual(parse_prefix(prefix(value)),value)
        for bad in ['__import__ os','+ R0 R4','+ R0','R0 R1',' '.join(['abs']*41)+' R0']:
            with self.assertRaises(ValueError):parse_prefix(bad)

    def test_register_augmentation_renames_text_and_code_together(self):
        row={'task':'В R0 запас, R1 потратили.','expression':['-','R0','R1']}
        value=renamed(row,('R3','R0','R1','R2'))
        self.assertEqual(value['task'],'В R3 запас, R0 потратили.')
        self.assertEqual(value['expression'],['-','R3','R0'])
        self.assertEqual(value['reference_code'],[0x63,0x60,0x11,0x50])

    def test_example_loss_keeps_short_answers_weighted(self):
        generator=torch.Generator().manual_seed(143);x=torch.randn(2,6,7,generator=generator,requires_grad=True)
        labels=torch.tensor([[-100,-100,1,-100,-100,-100],[-100,2,3,4,5,6]])
        a=F.cross_entropy(x[0,1:2],torch.tensor([1]))
        b=F.cross_entropy(x[1,:5],torch.tensor([2,3,4,5,6]))
        loss=example_loss(x,labels)
        self.assertAlmostEqual(float(loss.detach()),float(((a+b)/2).detach()),places=6)
        loss.backward();self.assertTrue(torch.isfinite(x.grad).all())

    def test_real_nonbyte_aligned_codes_roundtrip(self):
        rng=np.random.default_rng(413)
        for bits in [2,3,4]:
            codes=rng.integers(0,1<<bits,size=1024,dtype=np.uint8)
            packed=pack_codes(torch.from_numpy(codes),bits)
            self.assertEqual(len(packed),1024*bits//8)
            np.testing.assert_array_equal(unpack_codes(packed,bits,1024),codes)

    def test_model_reload_matches_quantizer_and_tied_weights(self):
        initial=BUILD/'distill-hard/export/baseline/hf'
        model=AutoModelForCausalLM.from_pretrained(initial,local_files_only=True,trust_remote_code=False)
        weights={n:p.detach().clone()for n,p in model.named_parameters()}
        with tempfile.TemporaryDirectory()as directory:
            for mode in FORMATS:
                for n,p in model.named_parameters():p.data.copy_(weights[n])
                report=export(model,Path(directory)/(mode+'.mkqb'),mode);header=load(model,report['file'])
                for row in header['tensors']:
                    expected=quantize(weights[row['name']],row['bits'])[2]if row['bits']!=32 else weights[row['name']]
                    self.assertTrue(torch.equal(model.get_parameter(row['name']).cpu(),expected),row['name'])
                self.assertIs(model.get_input_embeddings().weight,model.get_output_embeddings().weight)

    def test_qat_preserves_optimizer_parameters_and_plain_copy(self):
        initial=BUILD/'distill-hard/export/baseline/hf'
        model=AutoModelForCausalLM.from_pretrained(initial,local_files_only=True,trust_remote_code=False)
        ids={id(p)for p in model.parameters()};attach(model,'mixed')
        self.assertEqual(ids,{id(p)for p in model.parameters()})
        replica=plain_copy(model)
        self.assertEqual(ids,{id(p)for p in model.parameters()})
        self.assertIs(replica.get_input_embeddings().weight,replica.get_output_embeddings().weight)
        parameter=next(p for n,p in model.named_parameters()if'mlp' in n)
        module=model.model.layers[0].mlp.gate_proj
        module.weight.sum().backward()
        self.assertTrue(torch.equal(parameter.grad,torch.ones_like(parameter)))


if __name__=='__main__':
    torch.set_num_threads(2);unittest.main()
