"""Same effective starting model; continued rank16 versus all3,022,080 weights."""
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from be_common import ROOT,SOURCE,ACTION_IDS,CORRECT_IDS,body_ids,compact_head
from ay_model import Agent as LoRAParent
from ap_model import Agent as Interface
from af_model import aligned_q4
from native_quant import plain_master,attach,packed_copy
from lowbit import load as load_packet

class LoRA(LoRAParent):
    def __init__(self,device='cuda',checkpoint=None):super().__init__(device,checkpoint or ROOT/'initial-adapter.safetensors')

class AlignedQ4(torch.nn.Module):
    def forward(self,weight):return aligned_q4(weight)

class Full(Interface):
    def __init__(self,device='cuda',checkpoint=None):
        torch.nn.Module.__init__(self)
        self.base=AutoModelForCausalLM.from_pretrained(SOURCE/'hf',local_files_only=True).float()
        self.tokenizer=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True)
        self.base.requires_grad_(True)
        for name,module in list(self.base.named_modules()):
            if isinstance(module,(torch.nn.Linear,torch.nn.Embedding)):
                parametrize.register_parametrization(module,'weight',AlignedQ4())
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad}
        self.adapter_names=[];self.to(device);compact_head(self.base,body_ids(self.tokenizer))
        assert self.trainable_count()==3022080
        if checkpoint:self.load_checkpoint(checkpoint)
    def action_weight(self):return self.get_input_embeddings().weight[ACTION_IDS]
    def correct_weight(self):return self.get_input_embeddings().weight[CORRECT_IDS]
    @torch.no_grad()
    def merged_master(self):return plain_master(self.base)
    @torch.no_grad()
    def packed(self,path):
        master=self.merged_master();attach(master,'q4');return packed_copy(master,path,'q4')

def agent(arm,device='cuda',checkpoint=None):return (LoRA if arm=='lora'else Full)(device,checkpoint)

def load(folder=SOURCE,device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True).float();load_packet(model,folder/'model.mkqb')
    model.to(device).eval().requires_grad_(False)
    return model,AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
