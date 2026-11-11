"""Q4-aware adjustment of DIAG readout, without changing the encoder."""
import copy
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from ap_model import Agent as Parent
from af_model import aligned_q4
from lowbit import load as load_packet
from cd_common import ACTOR,ACTIONS,ACTION_IDS,CORRECT_IDS,body_ids,compact_head

ROWS=[ACTIONS.index(a)for a in ['diag']]

class Actor(Parent):
    def __init__(self,device='cpu',checkpoint=None):
        torch.nn.Module.__init__(self)
        self.base=AutoModelForCausalLM.from_pretrained(ACTOR/'hf',local_files_only=True).float()
        load_packet(self.base,ACTOR/'model.mkqb');self.base.requires_grad_(False)
        self.tokenizer=AutoTokenizer.from_pretrained(ACTOR/'hf',local_files_only=True)
        compact_head(self.base,body_ids(self.tokenizer));w=self.base.get_input_embeddings().weight
        self.action_head=torch.nn.Parameter(w[ACTION_IDS].detach().clone(),requires_grad=False)
        self.correct_head=torch.nn.Parameter(w[CORRECT_IDS].detach().clone(),requires_grad=False)
        self.decision_head=torch.nn.Parameter(self.action_head[ROWS].detach().clone())
        self.adapter_names=[];self.checkpoint_names={'decision_head'};self.to(device)
        assert self.trainable_count()==128
        if checkpoint:self.load_checkpoint(checkpoint)
    def master_action(self):return self.action_head.index_copy(0,torch.tensor(ROWS,device=self.action_head.device),self.decision_head)
    def action_weight(self):return aligned_q4(self.master_action())
    @torch.no_grad()
    def merged_master(self):
        replica=super().merged_master()
        replica.get_input_embeddings().weight[ACTION_IDS]=self.master_action().detach().cpu()
        replica.tie_weights();return replica.eval()
