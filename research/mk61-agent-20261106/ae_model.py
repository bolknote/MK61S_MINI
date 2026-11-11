"""Matched merged-Q4 starts; larger adapters versus a fully trainable transformer."""
import copy
import hashlib
from pathlib import Path
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM,AutoTokenizer
from safetensors.torch import save_file,load_file
from ae_common import INITIAL,INITIAL_PACKET,ACTION_IDS,CORRECT_IDS,body_ids,compact_head
from ac_model import LowRankQ4
from quantization import fake_q4
from native_quant import Fixed4,attach,packed_copy
from lowbit import load


class Agent(torch.nn.Module):
    def __init__(self,arm='lora16',device='cuda',checkpoint=None):
        super().__init__();assert arm in ['lora16','full'];self.arm=arm
        self.base=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(self.base,INITIAL_PACKET);self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
        weight=self.base.get_input_embeddings().weight
        self.action_head=torch.nn.Parameter(weight[ACTION_IDS].detach().clone())
        self.correct_head=torch.nn.Parameter(weight[[ACTION_IDS[0],ACTION_IDS[3]]].detach().clone())
        self.adapter_names=[]
        if arm=='full':
            for p in self.base.model.layers.parameters():p.requires_grad_(True)
            for p in self.base.model.norm.parameters():p.requires_grad_(True)
            for name,module in list(self.base.named_modules()):
                if isinstance(module,torch.nn.Linear)and name.startswith('model.layers.'):
                    parametrize.register_parametrization(module,'weight',Fixed4())
        else:
            for name,module in list(self.base.named_modules()):
                if name.endswith(('.self_attn.q_proj','.self_attn.v_proj','.mlp.gate_proj','.mlp.up_proj','.mlp.down_proj')):
                    parametrize.register_parametrization(module,'weight',LowRankQ4(module.weight.shape,rank=16,alpha=32));self.adapter_names.append(name)
        self.checkpoint_names={n for n,p in self.named_parameters()if p.requires_grad}
        self.to(device)
        if checkpoint:self.load_checkpoint(checkpoint)
        compact_head(self.base,body_ids(self.tokenizer))

    @property
    def model(self):return self.base.model
    @property
    def config(self):return self.base.config
    def get_input_embeddings(self):return self.base.get_input_embeddings()
    def generate(self,**kwargs):return self.base.generate(**kwargs)
    def action_weight(self):return fake_q4(self.action_head)
    def correct_weight(self):return fake_q4(self.correct_head)
    def input_digest(self):return hashlib.sha256(self.base.get_input_embeddings().weight.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
    def trainable_count(self):return sum(p.numel()for n,p in self.named_parameters()if n in self.checkpoint_names)

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
            if name.endswith('.weight'):
                module=self.base.get_submodule(name.rsplit('.',1)[0])
                if parametrize.is_parametrized(module,'weight'):
                    original=module.parametrizations.weight.original;quantizer=module.parametrizations.weight[0]
                    value=quantizer.master(original)if isinstance(quantizer,LowRankQ4)else original
                else:value=self.base.get_parameter(name)
            else:value=self.base.get_parameter(name)
            p.copy_(value.detach().cpu())
        replica.get_input_embeddings().weight[ACTION_IDS]=self.action_head.detach().cpu()
        replica.get_input_embeddings().weight[CORRECT_IDS]=self.correct_head.detach().cpu()
        replica.tie_weights();return replica.eval()

    @torch.no_grad()
    def packed(self,path):
        master=self.merged_master();attach(master,'q4');return packed_copy(master,path,'q4')


def action_weight(model):return model.action_weight()if isinstance(model,Agent)else model.get_input_embeddings().weight[ACTION_IDS]
def correct_weight(model):return model.correct_weight()if isinstance(model,Agent)else model.get_input_embeddings().weight[CORRECT_IDS]
