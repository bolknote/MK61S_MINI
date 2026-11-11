"""Continue each branch from its own selected clean-course checkpoint."""
from bj_common import ROOT,SOURCES
from be_model import LoRA as LoRAParent,Full as FullParent,load

class LoRA(LoRAParent):
    def __init__(self,device='cuda',checkpoint=None):super().__init__(device,checkpoint or ROOT/'initial-lora.safetensors')

class Full(FullParent):
    def __init__(self,device='cuda',checkpoint=None):super().__init__(device,checkpoint or ROOT/'initial-full.safetensors')

def agent(arm,device='cuda',checkpoint=None):return (LoRA if arm=='lora'else Full)(device,checkpoint)
def parent(arm,device='cuda'):return load(SOURCES[arm],device)
