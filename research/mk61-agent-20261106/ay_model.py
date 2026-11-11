"""Fresh, matched rank16 Q4 adapters on the latest AQ full 3M export."""
import hashlib
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from ap_model import Agent as Parent
from ac_model import LowRankQ4
from af_model import AlignedLowRank
from lowbit import load as load_packet
from ay_common import INITIAL,ACTION_IDS,CORRECT_IDS,body_ids,compact_head


class Agent(Parent):
    def __init__(self,device='cuda',checkpoint=None):
        torch.nn.Module.__init__(self)
        self.base=AutoModelForCausalLM.from_pretrained(INITIAL/'hf',local_files_only=True)
        load_packet(self.base,INITIAL/'model.mkqb');self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(INITIAL/'hf',local_files_only=True)
        compact_head(self.base,body_ids(self.tokenizer))
        weight=self.base.get_input_embeddings().weight
        self.action_head=torch.nn.Parameter(weight[ACTION_IDS].detach().clone())
        # Retain the old auxiliary rows, without training a new correctness critic.
        self.correct_head=torch.nn.Parameter(weight[CORRECT_IDS].detach().clone(),requires_grad=False)
        self.adapter_names=[]
        for name,module in list(self.base.named_modules()):
            if name.endswith(('.self_attn.q_proj','.self_attn.v_proj','.mlp.gate_proj','.mlp.up_proj','.mlp.down_proj')):
                with torch.random.fork_rng(devices=[]):
                    torch.manual_seed(int(hashlib.sha256(name.encode()).hexdigest()[:8],16))
                    old=LowRankQ4(module.weight.shape,rank=16,alpha=32)
                parametrize.register_parametrization(module,'weight',AlignedLowRank(old));self.adapter_names.append(name)
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad}
        self.to(device)
        if checkpoint:self.load_checkpoint(checkpoint)


def load(device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(INITIAL/'hf',local_files_only=True)
    load_packet(model,INITIAL/'model.mkqb');model.requires_grad_(False);model.to(device).eval()
    tokenizer=AutoTokenizer.from_pretrained(INITIAL/'hf',local_files_only=True)
    return model,tokenizer
