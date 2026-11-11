"""Fresh rank16 adapters over the same AJ terminal Q4 source."""
import hashlib
import torch
from torch.nn.utils import parametrize
from transformers import AutoModelForCausalLM, AutoTokenizer
from ae_model import Agent as Parent, action_weight, correct_weight
from ac_model import LowRankQ4
from af_model import AlignedLowRank, aligned_q4
from lowbit import load as load_packet
from al_common import INITIAL, INITIAL_PACKET, ACTION_IDS, CORRECT_IDS, body_ids, compact_head


def load(device='cuda'):
    model = AutoModelForCausalLM.from_pretrained(INITIAL, local_files_only=True)
    load_packet(model, INITIAL_PACKET); model.requires_grad_(False); model.to(device).eval()
    tokenizer = AutoTokenizer.from_pretrained(INITIAL, local_files_only=True)
    compact_head(model, body_ids(tokenizer))
    return model, tokenizer


class Agent(Parent):
    def __init__(self, arm='late', device='cuda', checkpoint=None):
        torch.nn.Module.__init__(self)
        assert arm in ['late', 'all']; self.arm = arm
        self.base, self.tokenizer = load('cpu')
        weight = self.base.get_input_embeddings().weight
        self.action_head = torch.nn.Parameter(weight[ACTION_IDS].detach().clone())
        self.correct_head = torch.nn.Parameter(weight[CORRECT_IDS].detach().clone())
        self.adapter_names = []
        for name, module in list(self.base.named_modules()):
            if not name.startswith('model.layers.'): continue
            layer = int(name.split('.')[2])
            if arm == 'late' and layer < 8: continue
            if name.endswith(('.self_attn.q_proj', '.self_attn.v_proj', '.mlp.gate_proj', '.mlp.up_proj', '.mlp.down_proj')):
                with torch.random.fork_rng(devices=[]):
                    torch.manual_seed(int(hashlib.sha256(name.encode()).hexdigest()[:8], 16))
                    old = LowRankQ4(module.weight.shape, rank=16, alpha=32)
                parametrize.register_parametrization(module, 'weight', AlignedLowRank(old))
                self.adapter_names.append(name)
        self.checkpoint_names = {n for n, p in self.named_parameters() if p.requires_grad}
        self.to(device)
        if checkpoint: self.load_checkpoint(checkpoint)

    def action_weight(self): return aligned_q4(self.action_head)
    def correct_weight(self): return aligned_q4(self.correct_head)
