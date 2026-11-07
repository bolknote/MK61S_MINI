"""Parameter/RAM design only: wider attention with matched Q4 vs Q2/Q4 budgets."""
import copy
import json
from pathlib import Path

import torch
from transformers import AutoConfig,AutoModelForCausalLM

from tasks import BUILD


def main():
    root=BUILD/'capacity-v1/proposed-mixed-design';root.mkdir(parents=True,exist_ok=True)
    base=AutoConfig.from_pretrained(BUILD/'flourish-original',local_files_only=True,trust_remote_code=False)
    rows={}
    for name,ffn,mode in [('q4-control',288,'q4'),('mixed-candidate',512,'mixed')]:
        cfg=copy.deepcopy(base);cfg.hidden_size=256;cfg.intermediate_size=ffn
        cfg.num_hidden_layers=10;cfg.num_attention_heads=8;cfg.num_key_value_heads=1;cfg.head_dim=32
        cfg.max_position_embeddings=2048
        with torch.device('meta'):model=AutoModelForCausalLM.from_config(cfg,trust_remote_code=False)
        counts={};payload=0;down_q4_extra=0
        for key,p in model.named_parameters():
            if p.ndim==2:
                bits=2 if mode=='mixed'and'.mlp.'in key else 4
                assert p.shape[-1]%32==0
                payload+=p.numel()*bits//8+p.numel()//32*2
                counts[str(bits)]=counts.get(str(bits),0)+p.numel()
                if mode=='mixed'and'.down_proj.'in key:down_q4_extra+=p.numel()*2//8
            else:payload+=p.numel()*4;counts['32']=counts.get('32',0)+p.numel()
        cfg.save_pretrained(root/name)
        rows[name]={'parameters':sum(p.numel()for p in model.parameters()),'hidden':256,'ffn':ffn,
          'query_heads':8,'kv_heads':1,'layers':10,'head_dim':32,'weight_counts_by_bits':counts,
          'packed_weight_payload_bytes':payload,'payload_mib':payload/1024**2,
          'fp16_kv_bytes_per_token':1280,'fp16_kv_1024_bytes':1310720,'fp16_kv_2048_bytes':2621440,
          'payload_if_down_projections_are_also_q4_bytes':payload+down_q4_extra}
    result={'status':'Architecture/RAM design only; no weights trained or quality measured',
      'models':rows,'same_attention_dimensions_and_kv':True,'group_size':32,'scale_bits':16,'norm_bits':32,
      'matrix_payload_includes_scales':True,'container_header_and_runtime_buffers_excluded':True,
      'serialized_tokenizer_json_bytes':(BUILD/'flourish-original/tokenizer.json').stat().st_size,
      'future_training':'Language continuation/distillation and full mixed-bit-aware course, followed by closed tests; context2048 needs training and validation',
      'extra_parameter_fraction':rows['mixed-candidate']['parameters']/rows['q4-control']['parameters']-1}
    (root/'design.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
