"""Auxiliary meaning/error heads are used only in training and dropped at export."""
import torch
from al_model import Agent as Parent, load, action_weight, correct_weight
from am_common import OPS, BINDINGS


class Agent(Parent):
    def __init__(self, arm='direct', device='cuda', checkpoint=None, probe=None):
        assert arm in ['direct', 'planned']; super().__init__('all', device, None); self.arm = arm
        self.op_head = torch.nn.Linear(128, len(OPS), device=device)
        self.binding_head = torch.nn.Linear(128, BINDINGS, device=device)
        self.error_head = torch.nn.Linear(128, 5, device=device)
        if probe:
            from safetensors.torch import load_file
            values = load_file(str(probe))
            with torch.no_grad():
                for name in ['op_head', 'binding_head']:
                    head = getattr(self, name); head.weight.copy_(values[name+'.weight'].to(device)); head.bias.copy_(values[name+'.bias'].to(device))
        self.checkpoint_names = {n for n, p in self.named_parameters() if p.requires_grad}
        if checkpoint: self.load_checkpoint(checkpoint)
