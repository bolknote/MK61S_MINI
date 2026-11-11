"""Expand depth with zero-output residual blocks, preserving the initial function."""
import copy
import json
import re
import shutil
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from br_common import ROOT,SOURCE,ARMS,read,write,rows,sha,ACTIONS,ACTION_IDS,output_ids,compact_head
from native_quant import attach,export
from lowbit import load as load_q4
from native_export import packet
from aq_protocol import prompt_ids
from bk_independent_generate import generate


def final_hidden(model,tok,prompt):
    ids=torch.tensor([prompt_ids(tok,prompt)])
    with torch.inference_mode():return model.model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).last_hidden_state


def main():
    ROOT.mkdir(exist_ok=True);assert not(ROOT/'frozen.json').exists()
    if(ROOT/'initialization.json').exists():return
    small=AutoModelForCausalLM.from_pretrained(SOURCE/'hf',local_files_only=True).float().eval()
    tok=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True)
    config=copy.deepcopy(small.config);config.num_hidden_layers=20;config.layer_types=['full_attention']*20
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(261120112);large=AutoModelForCausalLM.from_config(config).float().eval()
    with torch.no_grad():
        for n,p in small.named_parameters():
            match=re.match(r'model.layers.(\d+)\.(.*)',n)
            if match:
                i=int(match[1]);suffix=match[2]
                for j in [2*i,2*i+1]:large.get_parameter(f'model.layers.{j}.'+suffix).copy_(p)
            else:large.get_parameter(n).copy_(p)
        for i in range(10):
            layer=large.model.layers[2*i+1]
            for module in [layer.self_attn.o_proj,layer.mlp.down_proj]:
                for p in module.parameters():p.zero_()
        large.tie_weights()
    assert sum(p.numel()for p in small.parameters())==3022080
    assert sum(p.numel()for p in large.parameters())==4991360
    for n,p in small.named_parameters():
        match=re.match(r'model.layers.(\d+)\.(.*)',n)
        target=f'model.layers.{2*int(match[1])}.'+match[2]if match else n
        assert torch.equal(p,large.get_parameter(target)),n
    probes=read(ROOT/'initial-probes.json');hidden_checks={};exports={}
    for arm,model in [('small',small),('large',large)]:
        folder=ROOT/'initial'/arm;folder.mkdir(parents=True,exist_ok=True)
        model.save_pretrained(folder/'hf',safe_serialization=True);tok.save_pretrained(folder/'hf')
        q=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True).float().eval();attach(q,'q4');receipt=export(q,folder/'model.mkqb','q4')
        write(folder/'manifest.json',{'arm':'asm','output_arm':'spec','quantization_mode':'q4','parameter_count':sum(p.numel()for p in model.parameters()),
              'packed_sha256':sha(folder/'model.mkqb'),'packed_bytes':(folder/'model.mkqb').stat().st_size,
              'checkpoint_files':{p.name:sha(p)for p in(folder/'hf').iterdir()if p.is_file()},'capacity_diagnostic_only':True})
        exports[arm]=receipt
    assert packet(ROOT/'initial/small/model.mkqb')[1]==packet(SOURCE/'model.mkqb')[1]
    for precision in ['master','Q4']:
        models=[]
        for arm in ARMS:
            m=AutoModelForCausalLM.from_pretrained(ROOT/'initial'/arm/'hf',local_files_only=True).float().eval()
            if precision=='Q4':load_q4(m,ROOT/'initial'/arm/'model.mkqb')
            models.append(m)
        errors=[]
        for p in probes:
            a=final_hidden(models[0],tok,p['prompt']);b=final_hidden(models[1],tok,p['prompt'])
            errors.append(float((a-b).abs().max()));assert torch.equal(a,b),(precision,errors[-1])
        streams=[]
        for p in (probes[:6]if precision=='Q4'else[]):
            a=generate(models[0],tok,[p['prompt']],p['forced_action'])[0]
            b=generate(models[1],tok,[p['prompt']],p['forced_action'])[0]
            assert a['generated_token_ids']==b['generated_token_ids']
            streams.append({'action':a['action'],'input_tokens':a['input_tokens'],'token_streams_equal':True})
        hidden_checks[precision]={'prompts':len(probes),'max_abs_hidden_difference':max(errors),'streams':streams}
    write(ROOT/'initialization.json',{'complete':True,'parameter_counts':{'small':3022080,'large':4991360},'hidden_checks':hidden_checks,
          'mapped_parent_parameters_exact':True,'added_attention_and_MLP_outputs_zero':True,'small_Q4_payload_equals_parent':True,
          'same_vocabulary':True,'exports':exports,'optimizer_updates':0,'larger_model_not_deployed_to_device':True})
    print(json.dumps(read(ROOT/'initialization.json')),flush=True)


if __name__=='__main__':torch.set_num_threads(4);main()
