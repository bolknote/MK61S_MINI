"""Only 17,920 Q/V LoRA values and 640 action-head values receive updates.

The forward pass quantizes the merged Q/V matrix, so export uses the same Q4
function, rather than hoping that a later merge/quantization preserves behavior.
"""
import copy
import hashlib
from pathlib import Path
import torch
import torch.nn.functional as F
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from safetensors.torch import save_file,load_file
from ac_common import INITIAL,INITIAL_PACKET,ACTION_IDS,body_ids,compact_head
from quantization import fake_q4
from lowbit import load
from native_quant import attach,export,packed_copy


class LowRankQ4(torch.nn.Module):
    def __init__(self,shape,rank=4,alpha=8):
        super().__init__();out,inside=shape;self.scale=alpha/rank
        self.A=torch.nn.Parameter(torch.randn(rank,inside)*.025)
        self.B=torch.nn.Parameter(torch.zeros(out,rank))
    def master(self,weight):
        # Use FP32 for the small merge in both training and export.
        with torch.autocast(device_type=weight.device.type,enabled=False):
            return weight.float()+self.scale*(self.B.float()@self.A.float())
    def forward(self,weight):return fake_q4(self.master(weight)).to(weight.dtype)


class Agent(torch.nn.Module):
    def __init__(self,device='cuda',checkpoint=None):
        super().__init__()
        self.base=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True)
        load(self.base,INITIAL_PACKET);self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
        self.action_head=torch.nn.Parameter(self.base.get_input_embeddings().weight[
            [self.tokenizer.encode(c,add_special_tokens=False)[0]for c in ['w','r','t','d','u']]].detach().clone())
        self.adapter_names=[]
        for name,module in list(self.base.named_modules()):
            if name.endswith(('.self_attn.q_proj','.self_attn.v_proj')):
                parametrize.register_parametrization(module,'weight',LowRankQ4(module.weight.shape))
                self.adapter_names.append(name)
        self.to(device)
        if checkpoint:self.load_adapter(checkpoint)
        compact_head(self.base,body_ids(self.tokenizer))
        assert sum(p.numel()for p in self.parameters()if p.requires_grad)==18560

    @property
    def model(self):return self.base.model
    @property
    def config(self):return self.base.config
    @property
    def lm_head(self):return self.base.lm_head
    def get_input_embeddings(self):return self.base.get_input_embeddings()
    def generate(self,**kwargs):return self.base.generate(**kwargs)
    def head_weight(self):return fake_q4(self.action_head)
    def frozen_digest(self):
        h=hashlib.sha256()
        for name,p in self.base.named_parameters():
            if not name.endswith(('.0.A','.0.B')):
                h.update(name.encode());h.update(p.detach().cpu().contiguous().numpy().tobytes())
        return h.hexdigest()

    def save_adapter(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        save_file({n:p.detach().cpu().contiguous()for n,p in self.named_parameters()if n=='action_head'or n.endswith(('.0.A','.0.B'))},str(path))

    def load_adapter(self,path):
        values=load_file(str(path));params=dict(self.named_parameters())
        expected={n for n in params if n=='action_head'or n.endswith(('.0.A','.0.B'))};assert set(values)==expected
        with torch.no_grad():
            for n,w in values.items():params[n].copy_(w.to(params[n].device))

    @torch.no_grad()
    def merged_master(self):
        replica=AutoModelForCausalLM.from_config(copy.deepcopy(self.config)).cpu()
        for name,p in replica.named_parameters():
            if name.endswith('.weight')and name.rsplit('.',1)[0]in self.adapter_names:
                module=self.base.get_submodule(name.rsplit('.',1)[0])
                value=module.parametrizations.weight[0].master(module.parametrizations.weight.original)
            else:value=self.base.get_parameter(name)
            p.copy_(value.detach().cpu())
        replica.get_input_embeddings().weight[ACTION_IDS]=self.action_head.detach().cpu()
        replica.tie_weights();return replica.eval()

    @torch.no_grad()
    def packed(self,path):
        master=self.merged_master();attach(master,'q4');model,info=packed_copy(master,path,'q4')
        return model,info


def action_weight(model):
    return model.head_weight()if isinstance(model,Agent)else model.get_input_embeddings().weight[ACTION_IDS]


def decision_logits(model,ids,mask):
    hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
    selected=hidden[torch.arange(len(ids),device=ids.device),mask.sum(1)-1]
    return F.linear(selected,action_weight(model)).float()
