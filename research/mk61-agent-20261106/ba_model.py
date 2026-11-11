"""Continue the selected SPEC factors, preserving its original Q4 foundation."""
from ay_model import Agent as Parent
from ba_common import ROOT,SOURCE
from transformers import AutoModelForCausalLM,AutoTokenizer
from lowbit import load as load_packet

class Agent(Parent):
    def __init__(self,device='cuda',checkpoint=None):super().__init__(device,checkpoint or ROOT/'parent.safetensors')

def load(device='cuda'):
    model=AutoModelForCausalLM.from_pretrained(SOURCE/'hf',local_files_only=True);load_packet(model,SOURCE/'model.mkqb')
    model.to(device).eval().requires_grad_(False)
    return model,AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True)
