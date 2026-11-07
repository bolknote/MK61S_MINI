"""Activate duplicated hidden directions with cancelling Q4 input perturbations."""
import hashlib
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from native_quant import attach,restore_scales,save,packed_copy
from quantization import quantize_matrix
from tasks import BUILD


@torch.no_grad()
def activate(model,seed):
    generator=torch.Generator().manual_seed(seed);counts=[]
    for layer in model.model.layers:
        w=layer.self_attn.q_proj.parametrizations.weight.original
        codes,amp=quantize_matrix(w)
        assert torch.equal(codes[:,:4],codes[:,4:])and torch.equal(amp[:,:4],amp[:,4:])
        base=codes[:,:4].clone()
        mask=(base.abs()<=5)&(torch.rand(base.shape,generator=generator)<.2)
        sign=torch.randint(0,2,base.shape,generator=generator)*2-1
        delta=mask*sign
        left=base+delta;right=base-delta
        changed=torch.cat([left,right],1)*amp
        w.copy_(changed.reshape_as(w));counts.append(int(mask.sum()))
    return counts


def main():
    torch.set_num_threads(2);root=BUILD/'native-mixed-v1';target=root/'initial-active';target.mkdir(exist_ok=True)
    if(target/'manifest.json').exists():print('Activation already complete');return
    rows={}
    for arm in ['q4','mixed']:
        source=root/'warm-common-2000'/arm
        model=AutoModelForCausalLM.from_pretrained(source,local_files_only=True,trust_remote_code=False).eval()
        tokenizer=AutoTokenizer.from_pretrained(source,local_files_only=True,trust_remote_code=False)
        attach(model,arm);restore_scales(model,source)
        before,_=packed_copy(model,target/(arm+'-before.mkqb'),arm)
        counts=activate(model,6112101)
        after,packed=packed_copy(model,target/(arm+'.mkqb'),arm)
        preservation=[]
        with torch.no_grad():
            for text in ['Москва — столица России.','Из R2 вычти R0.','В коробке лежали красные и синие жетоны.','Программа читает исходные регистры.']:
                ids=torch.tensor([tokenizer.encode(text,add_special_tokens=False)])
                a=before(ids).logits;b=after(ids).logits
                preservation.append({'max_logit_error':float((a-b).abs().max()),'argmax_equal':bool(torch.equal(a.argmax(-1),b.argmax(-1)))})
        assert max(x['max_logit_error']for x in preservation)<.001 and all(x['argmax_equal']for x in preservation),preservation
        # Save the initial state before any diagnostic optimizer updates.
        save(model,tokenizer,target/arm,arm)
        ids=torch.tensor([tokenizer.encode('Сложи исходные значения R0 и R1 и получи результат.',add_special_tokens=False)])
        model(ids,labels=ids,use_cache=False).loss.backward()
        embed=model.get_input_embeddings().parametrizations.weight.original
        gradient_difference=float((embed.grad[:,:128]-embed.grad[:,128:]).norm())
        assert gradient_difference>0,gradient_difference
        optimizer=torch.optim.AdamW(model.parameters(),lr=1e-4);optimizer.step()
        weight_difference=float((embed[:,:128]-embed[:,128:]).abs().max().detach())
        assert weight_difference>0,weight_difference
        rows[arm]={'warm_source_sha256':hashlib.sha256((source/'model.safetensors').read_bytes()).hexdigest(),
          'changed_query_coefficients_per_layer':counts,'real_packed_preservation':preservation,'packed':packed,
          'embedding_gradient_half_difference_l2':gradient_difference,'embedding_half_difference_after_diagnostic_step':weight_difference,
          'diagnostic_updates_saved':False}
    result={'models':rows,'method':'Opposite integer Q4-code perturbations in duplicated input coordinates; maximum-code scale anchors untouched',
      'common_warmup_step':2000,'extra_language_tokens_each':100000000,'fresh_opened':False}
    (target/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result),flush=True)


if __name__=='__main__':main()
