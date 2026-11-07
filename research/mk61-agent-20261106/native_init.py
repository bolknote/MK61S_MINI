"""Project the Russian 128-wide foundation to a shared 256-wide, one-KV core.

K/V head averaging and FFN pruning are lossy. Only the subsequent 288→512
FFN expansion is function-preserving before quantization; verify that explicitly.
"""
import copy
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from tasks import BUILD
from native_quant import attach,packed_copy,save


@torch.no_grad()
def projected(source):
    cfg=copy.deepcopy(source.config);cfg.hidden_size=256;cfg.intermediate_size=288
    cfg.num_attention_heads=8;cfg.num_key_value_heads=1;cfg.head_dim=32;cfg.max_position_embeddings=2048
    result=AutoModelForCausalLM.from_config(cfg,trust_remote_code=False).eval();original=dict(source.named_parameters())
    selected={}
    for i,layer in enumerate(source.model.layers):
        mlp=layer.mlp
        salience=mlp.down_proj.weight.float().norm(dim=0)*mlp.up_proj.weight.float().norm(dim=1)
        selected[i]=salience.topk(288).indices.sort().values
    for name,value in result.named_parameters():
        old=original[name]
        if name=='model.embed_tokens.weight':value.copy_(old.repeat(1,2))
        elif name=='model.norm.weight':value.copy_(old.repeat(2)/2)
        elif '.input_layernorm.'in name or'.post_attention_layernorm.'in name:value.copy_(old.repeat(2))
        elif '.q_norm.'in name or'.k_norm.'in name:value.copy_(old)
        elif '.q_proj.weight'in name:
            # Four old queries/head group→eight, then average both old KV groups.
            w=old.reshape(4,32,128);w=w.repeat(2,1,1).reshape(256,128)
            value.copy_(w.repeat(1,2)/2)
        elif '.k_proj.weight'in name or'.v_proj.weight'in name:
            w=old.reshape(2,32,128).mean(0);value.copy_(w.repeat(1,2)/2)
        elif '.o_proj.weight'in name:value.copy_(old.repeat(2,2)/2)
        elif '.mlp.'in name:
            index=selected[int(name.split('.')[2])]
            if'down_proj'in name:value.copy_(old[:,index].repeat(2,1))
            else:value.copy_(old[index].repeat(1,2)/2)
        else:raise ValueError(name)
    result.tie_weights();return result


@torch.no_grad()
def expand(control):
    cfg=copy.deepcopy(control.config);cfg.intermediate_size=512
    grown=AutoModelForCausalLM.from_config(cfg,trust_remote_code=False).eval();old=dict(control.named_parameters())
    for name,value in grown.named_parameters():
        w=old[name]
        if value.shape==w.shape:value.copy_(w)
        elif'down_proj'in name:
            value[:,:288].copy_(w)
            # Opposite nonzero outputs cancel for duplicate incoming features,
            # while allowing the new incoming directions to learn immediately.
            amp=w.abs().amax(1,keepdim=True).clamp_min(.001)*.05
            value[:,288::2].copy_(amp.expand(-1,112));value[:,289::2].copy_(-amp.expand(-1,112))
        else:
            value[:288].copy_(w);value[288:].copy_(w[:112].repeat_interleave(2,dim=0))
    grown.tie_weights();return grown


def main():
    torch.set_num_threads(2);torch.manual_seed(6111501);root=BUILD/'native-mixed-v1';out=root/'initial';out.mkdir(parents=True,exist_ok=True)
    if(out/'manifest.json').exists():raise SystemExit('Initial weights already exist')
    source=AutoModelForCausalLM.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False).eval()
    tokenizer=AutoTokenizer.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False)
    control=projected(source);grown=expand(control);errors=[]
    with torch.no_grad():
        for text in ['Москва — столица России.','Из R2 вычти R0.','В коробке лежали красные и синие жетоны.','Программа МК-61 читает число из регистра.']:
            ids=torch.tensor([tokenizer.encode(text,add_special_tokens=False)])
            a=control(ids).logits;b=grown(ids).logits
            errors.append({'max_error':float((a-b).abs().max()),'argmax_equal':bool(torch.equal(a.argmax(-1),b.argmax(-1)))})
    assert max(x['max_error']for x in errors)<2e-4 and all(x['argmax_equal']for x in errors),errors
    models={}
    for name,model,mode in [('q4',control,'q4'),('mixed',grown,'mixed')]:
        count=sum(p.numel()for p in model.parameters());attach(model,mode)
        save(model,tokenizer,out/name,mode);replica,packed=packed_copy(model,out/(name+'.mkqb'),mode)
        # An actual QAT backward pass must reach the expanded input features.
        ids=torch.tensor([tokenizer.encode('Найди сумму R0 и R1.',add_special_tokens=False)])
        model(ids,labels=ids,use_cache=False).loss.backward()
        gradients={n:float(p.grad.float().norm())for n,p in model.named_parameters()if p.grad is not None and('layers.0.mlp.'in n)}
        assert all(v>0 for k,v in gradients.items()if'original'in k)
        models[name]={'parameters':count,'packed':packed,'gradient_norms_first_ffn':gradients,
          'learned_scale_parameters':sum(p.numel()for n,p in model.named_parameters()if n.endswith('.log_scale'))}
    report={'source':'Original Russian Flourish-3M, not the MK-61 audit-selected checkpoint',
      'source_sha256':hashlib.sha256((BUILD/'flourish-original/model.safetensors').read_bytes()).hexdigest(),
      'projection_to_256_and_single_KV_is_lossy':True,'ffn288_to512_fp32_preservation':errors,'models':models,
      'qat_from_first_training_step':True,'context2048_is_configured_not_yet_validated':True}
    (out/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report),flush=True)


if __name__=='__main__':main()
