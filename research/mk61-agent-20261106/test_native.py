"""Training/export invariants for the learned-scale mixed-bit comparison."""
import json
from pathlib import Path
import tempfile
import unittest

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from native_quant import attach,restore_scales,plain_master,save,packed_copy,Learned2
from native_language_train import loss_values
from tasks import BUILD
from native_activate import activate


class NativeTests(unittest.TestCase):
    def test_query_activation_preserves_forward_and_splits_hidden_gradient(self):
        model=AutoModelForCausalLM.from_pretrained(BUILD/'native-mixed-v1/initial/q4',local_files_only=True,trust_remote_code=False).eval()
        attach(model,'q4');tok=AutoTokenizer.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False)
        ids=torch.tensor([tok.encode('Исходные числа лежат в регистрах R0 и R1.',add_special_tokens=False)])
        with tempfile.TemporaryDirectory()as directory:
            a,_=packed_copy(model,Path(directory)/'before.mkqb','q4');activate(model,9021)
            b,_=packed_copy(model,Path(directory)/'after.mkqb','q4')
            with torch.no_grad():self.assertLess(float((a(ids).logits-b(ids).logits).abs().max()),.001)
        model(ids,labels=ids,use_cache=False).loss.backward()
        g=model.get_input_embeddings().parametrizations.weight.original.grad
        self.assertGreater(float((g[:,:128]-g[:,128:]).abs().sum()),0)

    def test_learned_amplitudes_survive_checkpoint_and_packet(self):
        model=AutoModelForCausalLM.from_pretrained(BUILD/'native-mixed-v1/initial/mixed',local_files_only=True,trust_remote_code=False)
        tok=AutoTokenizer.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False)
        attach(model,'mixed');restore_scales(model,BUILD/'native-mixed-v1/initial/mixed')
        with torch.no_grad():
            for module in model.modules():
                if isinstance(module,Learned2):module.log_scale.add_(.041)
        ids_before={id(p)for p in model.parameters()}
        with tempfile.TemporaryDirectory()as directory:
            d=Path(directory);save(model,tok,d/'hf','mixed')
            a,report=packed_copy(model,d/'a.mkqb','mixed')
            restored=AutoModelForCausalLM.from_pretrained(d/'hf',local_files_only=True,trust_remote_code=False)
            attach(restored,'mixed');restore_scales(restored,d/'hf');b,second=packed_copy(restored,d/'b.mkqb','mixed')
            self.assertEqual(report['payload_bytes'],3261952)
            for n,p in a.named_parameters():self.assertTrue(torch.equal(p,b.get_parameter(n)),n)
        self.assertEqual(ids_before,{id(p)for p in model.parameters()})

    def test_quantizer_scale_and_weight_both_learn(self):
        torch.manual_seed(771);w=torch.nn.Parameter(torch.randn(3,64)*.04);q=Learned2(w)
        before=q.log_scale.detach().clone();optimizer=torch.optim.AdamW([w,*q.parameters()],lr=.001)
        value=q(w);value.square().mean().backward()
        self.assertTrue(torch.isfinite(w.grad).all());self.assertGreater(float(w.grad.abs().sum()),0)
        self.assertTrue(torch.isfinite(q.log_scale.grad).all());self.assertGreater(float(q.log_scale.grad.abs().sum()),0)
        optimizer.step();self.assertFalse(torch.equal(before,q.log_scale))
        for row in q(w).reshape(3,-1,32):
            for group in row:self.assertLessEqual(len(torch.unique(group)),4)

    def test_causal_stream_alignment_matches_hf(self):
        model=AutoModelForCausalLM.from_pretrained(BUILD/'native-mixed-v1/initial/q4',local_files_only=True,trust_remote_code=False).eval()
        torch.manual_seed(772);window=torch.randint(10,8192,(2,18))
        with torch.no_grad():
            stock=model(window,labels=window,use_cache=False).loss
            custom=loss_values(model(window[:,:-1],use_cache=False).logits,None,window[:,1:])[0]
        self.assertAlmostEqual(float(stock),float(custom),places=5)


if __name__=='__main__':torch.set_num_threads(2);unittest.main()
