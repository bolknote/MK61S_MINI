"""Only unused output rows change; no trainable decoder or input rows."""
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from lowbit import load as load_packet
from af_model import aligned_q4
from ak_common import INITIAL,INITIAL_PACKET,ACTION_IDS,output_ids,compact_head


def load(device='cuda',heads=None):
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load_packet(model,INITIAL_PACKET)
    model.requires_grad_(False);model.to(device).eval()
    if heads is not None:set_heads(model,heads)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True);compact_head(model,output_ids(tokenizer))
    return model,tokenizer


@torch.no_grad()
def set_heads(model,heads):
    weight=model.get_input_embeddings().weight;weight[ACTION_IDS]=aligned_q4(heads.to(weight.device))

