"""The existing LoRA factors are continued, never replaced with a larger network."""
from af_common import START
from ae_model import Agent as Parent,action_weight,correct_weight
from ac_model import LowRankQ4
import torch


def aligned_q4(weight):
    # CUDA's approximate FP32 division can cross a Q4 or FP16-scale rounding
    # boundary. Match the existing CPU exporter, keeping its FP32 quotient
    # rounding before the FP16 scale conversion. STE forward is exactly the grid.
    groups=weight.float().reshape(weight.shape[0],-1,32)
    maximum=groups.abs().amax(-1,keepdim=True)
    scale=(maximum.double()/7).float().clamp_min(2**-24).to(torch.float16).float()
    codes=(groups.double()/scale.double()).float().round().clamp(-7,7)
    rounded=(codes*scale).reshape_as(weight).to(weight.dtype)
    return rounded.detach()+(weight-weight.detach())


class AlignedLowRank(LowRankQ4):
    def __init__(self,old):
        torch.nn.Module.__init__(self);self.scale=old.scale;self.A=old.A;self.B=old.B
    def forward(self,weight):return aligned_q4(self.master(weight)).to(weight.dtype)


class Agent(Parent):
    def __init__(self,arm='replay',device='cuda',checkpoint=None):
        assert arm in ['replay','contrast','initial']
        super().__init__('lora16',device,checkpoint or START)
        for name in self.adapter_names:
            module=self.base.get_submodule(name)
            module.parametrizations.weight[0]=AlignedLowRank(module.parametrizations.weight[0])
        self.training_arm=arm

    def action_weight(self):return aligned_q4(self.action_head)
    def correct_weight(self):return aligned_q4(self.correct_head)

