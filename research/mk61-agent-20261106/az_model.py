"""Continue the actual previous rank16 adapters, without changing capacity."""
from ay_model import Agent as Parent
from ay_common import compact_head,body_ids
from az_common import ROOT,SOURCES
from transformers import AutoModelForCausalLM,AutoTokenizer
from lowbit import load as load_packet


class Agent(Parent):
    def __init__(self,arm,device='cuda',checkpoint=None):
        assert arm in ['hex','spec']
        super().__init__(device,checkpoint or ROOT/('parent-'+arm+'.safetensors'))
        self.output_arm=arm


def load(arm,device='cuda'):
    folder=SOURCES[arm];model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True)
    load_packet(model,folder/'model.mkqb');model.to(device).eval().requires_grad_(False)
    tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
    return model,tokenizer
