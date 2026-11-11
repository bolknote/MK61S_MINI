"""Fully trained, same-Q4 models; only depth differs at matched initialization."""
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from br_common import ROOT,ACTION_IDS,CORRECT_IDS,body_ids,compact_head
from ap_model import Agent as Interface
from be_model import AlignedQ4
from native_quant import plain_master,attach,packed_copy
from lowbit import load as load_q4


class Full(Interface):
    def __init__(self,arm,device='cuda',checkpoint=None):
        torch.nn.Module.__init__(self);self.arm=arm;folder=ROOT/'initial'/arm/'hf'
        self.base=AutoModelForCausalLM.from_pretrained(folder,local_files_only=True).float()
        self.tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True);self.base.requires_grad_(True)
        for name,module in list(self.base.named_modules()):
            if isinstance(module,(torch.nn.Linear,torch.nn.Embedding)):parametrize.register_parametrization(module,'weight',AlignedQ4())
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad};self.adapter_names=[]
        self.to(device);compact_head(self.base,body_ids(self.tokenizer))
        if checkpoint:self.load_checkpoint(checkpoint)
    def action_weight(self):return self.get_input_embeddings().weight[ACTION_IDS]
    def correct_weight(self):return self.get_input_embeddings().weight[CORRECT_IDS]
    @torch.no_grad()
    def merged_master(self):return plain_master(self.base)
    @torch.no_grad()
    def packed(self,path):
        m=self.merged_master();attach(m,'q4');return packed_copy(m,path,'q4')


def load(arm,device='cuda'):
    folder=ROOT/'initial'/arm
    m=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True).float();load_q4(m,folder/'model.mkqb')
    m.to(device).eval().requires_grad_(False)
    return m,AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
