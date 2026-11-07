import types
import unittest

import torch
import torch.nn.functional as F

from codec_train import compact_loss


class Tiny(torch.nn.Module):
    def __init__(self):
        super().__init__();self.embedding=torch.nn.Embedding(8224,32)
    def get_input_embeddings(self):return self.embedding
    def model(self,input_ids,**kwargs):return types.SimpleNamespace(last_hidden_state=self.embedding(input_ids))


class LossTests(unittest.TestCase):
    def test_mixed_rows_equal_separate_per_example_ce(self):
        torch.manual_seed(6114523);m=Tiny()
        ids=torch.tensor([[4,5,8192,2],[9,8,7,2]]);mask=torch.ones_like(ids)
        labels=torch.tensor([[-100,-100,8192,2],[-100,8,7,2]])
        allowed=torch.tensor([2,4,5,8192]);lm=torch.tensor([False,True])
        actual=compact_loss(m,ids,mask,labels,lm,allowed)
        hidden=m.embedding(ids)[:,:-1];expected=[]
        for row,rows in [(0,allowed),(1,torch.arange(8192))]:
            valid=labels[row,1:]!=-100;target=labels[row,1:][valid]
            local=torch.tensor([rows.tolist().index(t)for t in target.tolist()])
            expected.append(F.cross_entropy(F.linear(hidden[row][valid],m.embedding.weight[rows]),local))
        self.assertTrue(torch.allclose(actual,torch.stack(expected).mean(),atol=1e-6))
        actual.backward();self.assertGreater(float(m.embedding.weight.grad[8192:].norm()),0)

    def test_missing_output_target_cannot_be_silently_ignored(self):
        m=Tiny();ids=torch.tensor([[4,8192,2]]);labels=ids.clone()
        with self.assertRaises(ValueError):compact_loss(m,ids,torch.ones_like(ids),labels,torch.tensor([False]),torch.tensor([2,4]))


if __name__=='__main__':unittest.main()
