"""Preserve both selected Q4 functions, extend3M config and probe2048 backward."""
import copy
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from compose_common import ROOT,sha
from lowbit import load
from native_quant import attach,save,packed_copy
from quantization import load_q4
from tasks import BUILD


def main():
    out=ROOT/'initial';out.mkdir(exist_ok=True)
    if(out/'manifest.json').exists():print('Both initial packets already verified');return
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    sources={'champion':BUILD/'native-mixed-v1/export/selected-budget',
             'small':BUILD/'capacity-v1/export/selected-budget'}
    frozen=json.loads((ROOT/'frozen.json').read_text());records={}
    for arm,folder in sources.items():
        packet=folder/('model.mkqb'if arm=='champion'else'model.mkq4')
        assert sha(packet)==frozen['source_packets'][arm]
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        reference=copy.deepcopy(model)
        (load if arm=='champion'else load_q4)(reference,packet)
        model.config.max_position_embeddings=2048;tokenizer.model_max_length=2048;attach(model,'q4')
        replica,packed=packed_copy(model,out/(arm+'-initial.mkqb'),'q4')
        error=max(float((p-reference.get_parameter(n)).abs().max())for n,p in replica.named_parameters())
        assert error==0.,error
        save(model,tokenizer,out/arm,'q4')
        # Diagnostic gradients are never saved or applied as optimizer updates.
        model.to('cuda').train();torch.cuda.reset_peak_memory_stats()
        ids=torch.randint(10,8192,(4,2048),device='cuda');labels=ids.clone();labels[:,:-64]=-100
        with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(ids,labels=labels,use_cache=False).loss
        assert torch.isfinite(loss);loss.backward()
        assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
        kv=2*model.config.num_hidden_layers*model.config.num_key_value_heads*model.config.head_dim*2
        records[arm]={'source_packet_sha256':sha(packet),'source_master_sha256':sha(folder/'hf/model.safetensors'),
          'packet':packed,'initial_dequantized_max_error':error,'configured_context':2048,
          'fp16_kv_bytes_per_token':kv,'2048_backward_finite':True,'probe_peak_cuda_bytes':torch.cuda.max_memory_allocated(),
          'diagnostic_optimizer_steps_saved':0}
        del model,reference,replica,ids,labels,loss;torch.cuda.empty_cache()
    (out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print(json.dumps(records),flush=True)


if __name__=='__main__':main()
