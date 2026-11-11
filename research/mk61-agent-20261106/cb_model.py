"""Fresh rank16 QAT adapters over the immutable tool actor, with frozen heads."""
import hashlib
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from ap_model import Agent as Parent
from ac_model import LowRankQ4
from af_model import AlignedLowRank
from lowbit import load as load_packet
from cb_common import ACTOR,ACTION_IDS,CORRECT_IDS,body_ids,compact_head


class Actor(Parent):
    def __init__(self,device='cpu',checkpoint=None):
        torch.nn.Module.__init__(self)
        self.base=AutoModelForCausalLM.from_pretrained(ACTOR/'hf',local_files_only=True).float()
        load_packet(self.base,ACTOR/'model.mkqb');self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True)
        compact_head(self.base,body_ids(self.tokenizer));weight=self.base.get_input_embeddings().weight
        self.action_head=torch.nn.Parameter(weight[ACTION_IDS].detach().clone(),requires_grad=False)
        self.correct_head=torch.nn.Parameter(weight[CORRECT_IDS].detach().clone(),requires_grad=False)
        self.adapter_names=[]
        for name,module in list(self.base.named_modules()):
            if name.endswith(('.self_attn.q_proj','.self_attn.v_proj','.mlp.gate_proj','.mlp.up_proj','.mlp.down_proj')):
                with torch.random.fork_rng(devices=[]):
                    torch.manual_seed(int(hashlib.sha256(('cb:'+name).encode()).hexdigest()[:8],16))
                    old=LowRankQ4(module.weight.shape,rank=16,alpha=32)
                parametrize.register_parametrization(module,'weight',AlignedLowRank(old));self.adapter_names.append(name)
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad};self.to(device)
        assert self.trainable_count()==317440
        if checkpoint:self.load_checkpoint(checkpoint)
