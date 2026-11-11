"""A standalone four-class Q4 critic, using four previously unused rows."""
import copy
import hashlib
from pathlib import Path
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from safetensors.torch import save_file,load_file
from ac_model import LowRankQ4
from af_model import AlignedLowRank,aligned_q4
from lowbit import load as load_packet
from native_quant import attach,packed_copy
from ao_common import INITIAL,INITIAL_PACKET,DIAG_IDS


def load(device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load_packet(model,INITIAL_PACKET)
    model.requires_grad_(False);model.to(device).eval();tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    return model,tokenizer


class Agent(torch.nn.Module):
    def __init__(self,arm='adapt',device='cuda',checkpoint=None):
        super().__init__();assert arm in ['head','adapt'];self.arm=arm;self.base,self.tokenizer=load('cpu');self.adapter_names=[]
        self.diagnosis_head=torch.nn.Parameter(self.base.get_input_embeddings().weight[DIAG_IDS].detach().clone())
        if arm=='adapt':
            for name,module in list(self.base.named_modules()):
                if name.endswith(('.self_attn.q_proj','.self_attn.v_proj','.mlp.gate_proj','.mlp.up_proj','.mlp.down_proj')):
                    with torch.random.fork_rng(devices=[]):
                        torch.manual_seed(int(hashlib.sha256(name.encode()).hexdigest()[:8],16));old=LowRankQ4(module.weight.shape,rank=16,alpha=32)
                    parametrize.register_parametrization(module,'weight',AlignedLowRank(old));self.adapter_names.append(name)
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad};self.to(device)
        if checkpoint:self.load_checkpoint(checkpoint)

    @property
    def model(self):return self.base.model
    @property
    def config(self):return self.base.config
    def get_input_embeddings(self):return self.base.get_input_embeddings()
    def head(self):return aligned_q4(self.diagnosis_head)
    def input_digest(self):return hashlib.sha256(self.base.get_input_embeddings().weight.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
    def trainable_count(self):return sum(p.numel()for p in self.parameters()if p.requires_grad)

    def save_checkpoint(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        save_file({n:p.detach().cpu().contiguous()for n,p in self.named_parameters()if n in self.checkpoint_names},str(path))

    def load_checkpoint(self,path):
        values=load_file(str(path));params=dict(self.named_parameters());assert set(values)==self.checkpoint_names
        with torch.no_grad():
            for n,w in values.items():params[n].copy_(w.to(params[n].device))

    @torch.no_grad()
    def merged_master(self):
        replica=AutoModelForCausalLM.from_config(copy.deepcopy(self.config)).cpu()
        for name,p in replica.named_parameters():
            if name.endswith('.weight')and name.rsplit('.',1)[0]in self.adapter_names:
                module=self.base.get_submodule(name.rsplit('.',1)[0]);value=module.parametrizations.weight[0].master(module.parametrizations.weight.original)
            else:value=self.base.get_parameter(name)
            p.copy_(value.detach().cpu())
        replica.get_input_embeddings().weight[DIAG_IDS]=self.diagnosis_head.detach().cpu();replica.tie_weights();return replica.eval()

    @torch.no_grad()
    def packed(self,path):
        master=self.merged_master();attach(master,'q4');return packed_copy(master,path,'q4')


def head(model):return model.head()if isinstance(model,Agent)else model.get_input_embeddings().weight[DIAG_IDS]
