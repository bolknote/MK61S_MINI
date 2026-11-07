"""The action gradient must not shrink with a longer serialized program."""
from types import SimpleNamespace
import torch
from aa_course import separate_loss,preference_loss
from aa_common import ACTION_IDS


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__();self.weight=torch.nn.Parameter(torch.zeros(8224,4))
    @property
    def model(self):return self
    def get_input_embeddings(self):return SimpleNamespace(weight=self.weight)
    def forward(self,input_ids,attention_mask,use_cache=False):
        return SimpleNamespace(last_hidden_state=torch.ones((*input_ids.shape,4)))


def batch(length):
    values=[10,11,ACTION_IDS[0]]+[18]*length+[2]
    ids=torch.tensor([values]);labels=torch.tensor([[-100]*3+[18]*length+[2]])
    return ids,torch.ones_like(ids),labels,torch.tensor([1]),torch.tensor([0]),torch.tensor([False])


def main():
    model=Toy();head=torch.tensor([2,18,19]);gradients=[]
    for length in [1,50,200]:
        model.zero_grad(set_to_none=True);loss,parts=separate_loss(model,batch(length),head);loss.backward()
        gradients.append(model.weight.grad[ACTION_IDS].clone())
        assert abs(parts['action']-float(torch.tensor(7.).log()))<1e-6
    assert all(torch.equal(gradients[0],g)for g in gradients[1:])
    reference=Toy();ids=torch.tensor([[10,11]]);mask=torch.ones_like(ids)
    model.zero_grad(set_to_none=True);loss=preference_loss(model,reference,ids,mask,torch.tensor([0]),torch.tensor([5]),.2)
    assert abs(float(loss.detach())-float(torch.tensor(2.).log()))<1e-6
    loss.backward()
    assert model.weight.grad[ACTION_IDS[0]].sum()<0 and model.weight.grad[ACTION_IDS[5]].sum()>0
    print({'action_gradients_identical_at_body_lengths':[1,50,200],'DPO_pushes_chosen_over_rejected':True})


if __name__=='__main__':main()
