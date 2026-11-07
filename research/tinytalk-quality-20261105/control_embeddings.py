"""Keep artificial control-token inputs independent from their output classifier."""
import torch
from torch import nn
from torch.nn import functional as F


class ControlEmbedding(nn.Embedding):
    def __init__(self, original, base, rows, initial=None):
        super().__init__(original.num_embeddings, original.embedding_dim,
            padding_idx=original.padding_idx, max_norm=original.max_norm,
            norm_type=original.norm_type, scale_grad_by_freq=original.scale_grad_by_freq,
            sparse=original.sparse, device=original.weight.device, dtype=original.weight.dtype)
        self.weight=original.weight
        self.control_base=base;self.control_rows=rows
        # A small explicit FP32 vector table, alongside the existing FP32 norms.
        values=torch.zeros(rows*self.embedding_dim,device=self.weight.device,dtype=torch.float32)
        if initial is not None:values.copy_(initial.reshape(-1))
        self.control_flat=nn.Parameter(values)

    def forward(self, indices):
        ordinary=super().forward(indices)
        selected=(indices>=self.control_base)&(indices<self.control_base+self.control_rows)
        positions=(indices-self.control_base).clamp(0,self.control_rows-1)
        controls=F.embedding(positions,self.control_flat.view(self.control_rows,self.embedding_dim))
        return torch.where(selected.unsqueeze(-1),controls,ordinary)


def install(model, initial=None):
    cfg=model.config;base=cfg.tinytalk_control_input_base_id;rows=cfg.tinytalk_control_input_rows
    assert base==cfg.tinytalk_answer_type_base_vocab_size and base+rows==cfg.vocab_size
    original=model.transformer.wte
    model.transformer.wte=ControlEmbedding(original,base,rows,initial)
    assert model.lm_head.weight is model.transformer.wte.weight
