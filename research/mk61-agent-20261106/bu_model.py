"""Fresh QAT LoRA in translation phases; no action/embedding updates."""
import hashlib
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from ap_model import Agent as Parent
from ac_model import LowRankQ4
from af_model import AlignedLowRank
from lowbit import load as load_packet
from bu_common import SOURCE,ACTION_IDS,CORRECT_IDS,body_ids,compact_head
from bs_model import parent as actor


class Translator(Parent):
    def __init__(self,device='cpu',checkpoint=None):
        torch.nn.Module.__init__(self)
        self.base=AutoModelForCausalLM.from_pretrained(SOURCE/'hf',local_files_only=True).float()
        load_packet(self.base,SOURCE/'model.mkqb');self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True)
        compact_head(self.base,body_ids(self.tokenizer));weight=self.base.get_input_embeddings().weight
        self.action_head=torch.nn.Parameter(weight[ACTION_IDS].detach().clone(),requires_grad=False)
        self.correct_head=torch.nn.Parameter(weight[CORRECT_IDS].detach().clone(),requires_grad=False)
        self.adapter_names=[]
        for name,module in list(self.base.named_modules()):
            if name.endswith(('.self_attn.q_proj','.self_attn.v_proj','.mlp.gate_proj','.mlp.up_proj','.mlp.down_proj')):
                with torch.random.fork_rng(devices=[]):
                    torch.manual_seed(int(hashlib.sha256(('bu:'+name).encode()).hexdigest()[:8],16))
                    old=LowRankQ4(module.weight.shape,rank=16,alpha=32)
                parametrize.register_parametrization(module,'weight',AlignedLowRank(old));self.adapter_names.append(name)
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad};self.to(device)
        assert all(n.endswith(('.0.A','.0.B'))for n in self.checkpoint_names)
        if checkpoint:self.load_checkpoint(checkpoint)


def frozen_digest(model):
    h=hashlib.sha256()
    for n,p in model.named_parameters():
        if not p.requires_grad:h.update(n.encode());h.update(p.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()
