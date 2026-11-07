"""Package a validation-selected checkpoint and verify its real low-bit reload."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from lowbit import export,load,quantize,bits_for
from quantization import export_q4,load_q4,quantize_matrix


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--format',choices=['q4','q3','q2','mixed'],required=True);a=p.parse_args();torch.set_num_threads(2)
    model=AutoModelForCausalLM.from_pretrained(a.model,local_files_only=True,trust_remote_code=False).eval()
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    a.output.mkdir(parents=True,exist_ok=True);model.save_pretrained(a.output/'hf',safe_serialization=True);tokenizer.save_pretrained(a.output/'hf')
    original_source=Path(__file__).resolve().parents[2]/'.build/mk61-agent-20261106/flourish-original'
    for filename,target in [('README.md','original-model-card.md'),('origin.json','original-origin.json')]:
        if(original_source/filename).exists():shutil.copyfile(original_source/filename,a.output/target)
    path=a.output/('model.mkq4'if a.format=='q4'else'model.mkqb')
    original={n:p.detach().clone()for n,p in model.named_parameters()}
    if a.format=='q4':packed=export_q4(model,path);load_q4(model,path)
    else:packed=export(model,path,a.format);load(model,path)
    error=0.
    for name,parameter in model.named_parameters():
        value=original[name]
        if value.ndim==2:
            if a.format=='q4':
                codes,scales=quantize_matrix(value);expected=(codes*scales).reshape_as(value)
            else:expected=quantize(value,bits_for(name,a.format))[2]
        else:expected=value
        error=max(error,float((parameter-expected).abs().max()))
    assert error==0.,error
    assert model.get_input_embeddings().weight is model.get_output_embeddings().weight
    config=model.config;per_token=2*config.num_hidden_layers*config.num_key_value_heads*config.head_dim*2
    result={'source_model':str(a.model),'source_hf_sha256':hashlib.sha256((a.model/'model.safetensors').read_bytes()).hexdigest(),
      'format':a.format,'packed':packed,'packed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'packed_bytes':path.stat().st_size,'parameters':sum(p.numel()for p in model.parameters()),
      'reload_max_error_vs_quantizer':error,'tied_embedding_output_preserved':True,
      'serialized_tokenizer_json_bytes':(a.output/'hf/tokenizer.json').stat().st_size,
      'fp16_kv_bytes_per_token':per_token,'fp16_kv_512_bytes':per_token*512,
      'host_inference_activations_and_kv':'FP32','native_device_memory_and_speed_measured':False,
      'context':512,'provenance':'akanemind/Flourish-3M; revision33b38dfec202c39c3698f7f2d1a9933a34a2de1a; user-authorized private training'}
    (a.output/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
