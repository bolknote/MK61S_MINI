#!/usr/bin/env python3
"""Add trainable MLP units while preserving initial Q4 behavior and the 8 MiB budget."""
import argparse
import copy
import json
from pathlib import Path
import shutil

from common import core, decode, load_model, logps, qat_modules, quantize


def main():
    import torch
    from transformers import AutoModelForCausalLM
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--tokenizer-table',required=True)
    p.add_argument('--intermediate',type=int,default=1280)
    p.add_argument('--device',default='cpu')
    p.add_argument('--seed',type=int,default=891471)
    args=p.parse_args()
    out=Path(args.output);assert not out.exists()
    model,tokenizer,device=load_model(args)
    model.eval().requires_grad_(False)
    config=copy.deepcopy(model.config)
    old=config.intermediate_size or config.hidden_size*4
    assert old==1024 and args.intermediate==1280
    source_sha=core.digest(Path(args.model)/'model.safetensors')
    config.intermediate_size=args.intermediate
    config.tinytalk_mlp_expansion={'source_sha256':source_sha,'old_width':old,'new_width':args.intermediate,
        'method':'Noisy copies of input units; zero new output columns; no initial functional contribution'}
    wider=AutoModelForCausalLM.from_config(config,attn_implementation='eager').to(device).eval().requires_grad_(False)
    source=model.state_dict()
    with torch.no_grad():
        for name,target in wider.state_dict().items():
            original=source[name]
            if target.shape==original.shape:
                target.copy_(original)
            elif name.endswith('mlp.c_fc.weight'):
                target[:old].copy_(original)
                target[old:].copy_(original[:args.intermediate-old]+torch.randn_like(target[old:])*.005)
            elif name.endswith('mlp.c_fc.bias'):
                target[:old].copy_(original);target[old:].copy_(original[:args.intermediate-old])
            elif name.endswith('mlp.c_proj.weight'):
                target.zero_();target[:,:old].copy_(original)
            else:
                raise ValueError(f'Unexpected expanded tensor {name}')
    probes=[]
    for index,(noun,value) in enumerate([('bag','green'),('cup','white'),('kite','orange'),('scarf','purple')]):
        probes.append({'id':f'expansion:{index}','messages':[{'role':'user','content':f'My {noun} is {value}.'},
            {'role':'assistant','content':'Okay, I understand.'},{'role':'user','content':f'What color is my {noun}?'}]})
    probes += [{'id':f'expansion:social:{i}','messages':[{'role':'user','content':text}]} for i,text in enumerate([
        'I would enjoy a little chat.','Please ask about my day.','I finished making a small paper bird.',
        'My friend enjoyed the present.','I changed my mind about the game.','I will come back to talk later.'])]
    batches=[]
    for row in probes:
        batch=tokenizer(core.render(row['messages']),return_tensors='pt',add_special_tokens=False)
        batches.append({k:v.to(device) for k,v in batch.items() if k in ['input_ids','attention_mask']})
    def difference():
        with torch.inference_mode():
            return max(float((model(**b,use_cache=False).logits-wider(**b,use_cache=False).logits).abs().max()) for b in batches)
    def inherited_tensors():
        targets=dict(wider.named_parameters());checks=[]
        for name,value in model.named_parameters():
            target=targets[name]
            if target.shape==value.shape:inherited=target
            elif name.endswith('mlp.c_fc.weight') or name.endswith('mlp.c_fc.bias'):inherited=target[:old]
            elif name.endswith('mlp.c_proj.weight'):
                inherited=target[:,:old];assert not target[:,old:].count_nonzero()
            else:raise ValueError(name)
            assert torch.equal(value,inherited),f'Inherited weights changed: {name}'
            checks.append(name)
        return checks
    raw_checks=inherited_tensors()
    fp32_error=difference();assert fp32_error<1e-4,fp32_error
    out.mkdir()
    wider.save_pretrained(out,safe_serialization=True);tokenizer.save_pretrained(out)
    quantize.copy_notices(args.model,out)
    for name in ['LANGUAGE_DATA.md']:
        path=Path(args.model)/name
        if path.exists():shutil.copyfile(path,out/name)
    shutil.copyfile(args.tokenizer_table,out/'tokenizer.ttbpe')
    backbone=getattr(model.config,'tinytalk_backbone',{})
    packed=quantize.export(wider,out/'model.ttq4',{'model':backbone.get('repository'),
        'revision':backbone.get('revision'),'source_sha256':source_sha,'recipe':'Function-preserving MLP expansion before training'})
    quantize.roundtrip(model);quantize.roundtrip(wider)
    # Inherited Q4 tensors must be bitwise identical. A wider GEMM can change
    # FP32 accumulation order even when its added output columns are all zero.
    inherited_checks=inherited_tensors()
    q4_error=difference();assert q4_error<1e-4,q4_error
    before=decode(model,tokenizer,probes,device);after=decode(wider,tokenizer,probes,device)
    exact=sum(a['raw_token_ids']==b['raw_token_ids'] for a,b in zip(before,after))
    assert exact==len(probes)
    expected={name:v.detach().clone() for name,v in wider.named_parameters()}
    quantize.restore(wider,out/'model.ttq4')
    reload_error=max(float((expected[name]-v).abs().max()) for name,v in wider.named_parameters())
    assert reload_error==0
    total=packed['file_bytes']+(out/'tokenizer.ttbpe').stat().st_size+1048576+262144
    assert total<8388608,total
    # This isolated two-step gradient diagnostic is performed AFTER saving.
    # Its updated parameters are never saved or used as a student initializer.
    wider.train().requires_grad_(True);qat_modules(wider)
    encoded,skipped=core.encode_rows(tokenizer,[dict(r,target='Green.',kind='diagnostic') for r in probes[:1]],128)
    assert encoded and not skipped
    optimizer=torch.optim.SGD(wider.parameters(),lr=.001)
    gradients=[]
    for step in range(2):
        optimizer.zero_grad(set_to_none=True)
        _,loss,_,_=logps(wider,encoded,tokenizer,device)
        loss.backward()
        input_norms=[float(b.mlp.c_fc.parametrizations.weight.original.grad[old:].norm()) for b in wider.transformer.h]
        output_norms=[float(b.mlp.c_proj.parametrizations.weight.original.grad[:,old:].norm()) for b in wider.transformer.h]
        gradients.append({'step':step,'new_input_gradient_norms':input_norms,'new_output_gradient_norms':output_norms})
        assert all(v>0 for v in output_norms)
        if step:assert all(v>0 for v in input_norms)
        optimizer.step()
    report={'source_sha256':source_sha,'parameters':sum(p.numel() for p in wider.parameters()),
        'old_width':old,'new_width':args.intermediate,'fp32_max_abs_logit_error':fp32_error,
        'q4_max_abs_logit_error':q4_error,'identical_probe_token_sequences':exact,'probe_count':len(probes),
        'inherited_q4_tensors_bitwise_identical':len(inherited_checks),
        'inherited_fp32_tensors_exact':len(raw_checks),'fp32_logit_tolerance':1e-4,
        'new_output_columns_exactly_zero':True,'q4_logit_tolerance':1e-4,
        'packed_reload_max_abs_error':reload_error,'packed':packed,'total_design_bytes':total,
        'remaining_from_8mib':8388608-total,'reserve_bytes':262144,'fp16_kv_bytes_context128':1048576,
        'new_capacity_gradient_check':gradients,'saved_initializer_is_untrained':True,'native_runtime_measured':False}
    core.save(out/'expansion.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['packed','new_capacity_gradient_check']}),flush=True)


if __name__=='__main__':
    main()
