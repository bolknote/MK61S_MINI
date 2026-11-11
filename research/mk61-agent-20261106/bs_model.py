"""Same working 3M QAT initialization as the verified capacity control."""
from br_model import Full
from be_model import load
from bs_common import SOURCE


def agent(device='cuda',checkpoint=None):return Full('small',device,checkpoint)
def parent(device='cuda'):return load(SOURCE,device)
