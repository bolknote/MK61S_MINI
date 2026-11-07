"""Identical enlarged initial weights for both formats, then no-update GPU preflight."""
import argparse
import collections
import gc
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from codec_common import ROOT,ARMS,OLD_VOCAB,read,sha,allowed_ids,protocol
from codec_train import Course,compact_loss
from lowbit import load
from native_quant import attach,save,packed_copy
from tasks import BUILD


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);a=p.parse_args()
    out=ROOT/'initial'/a.arm;out.mkdir(parents=True,exist_ok=True)
    if(out/'manifest.json').exists():
        manifest=json.loads((out/'manifest.json').read_text());assert manifest['frozen_sha256']==sha(ROOT/'frozen.json');print('Matching initialization complete');return
    frozen=json.loads((ROOT/'frozen.json').read_text())
    for name,entry in frozen['files'].items():assert sha(ROOT/name)==entry['sha256'],name
    source=BUILD/'composition-v1/export'/a.arm
    assert sha(source/'model.mkqb')==frozen['source_packets'][a.arm]
    assert sha(source/'hf/model.safetensors')==frozen['source_masters'][a.arm]
    torch.set_num_threads(4);torch.manual_seed(6114513);torch.cuda.set_per_process_memory_fraction(.45)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'tokenizer',local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(source/'hf',local_files_only=True,trust_remote_code=False)
    reference=AutoModelForCausalLM.from_pretrained(source/'hf',local_files_only=True,trust_remote_code=False);load(reference,source/'model.mkqb')
    old=model.get_input_embeddings().weight.detach().clone();model.resize_token_embeddings(OLD_VOCAB+32,mean_resizing=False)
    frequencies=collections.Counter(x for task in read(ROOT/'train.jsonl')for x in task['reference_code'])
    codec=protocol('h32').codec
    with torch.no_grad():
        rows=torch.zeros((32,old.shape[1]));counts=torch.zeros(32)
        for byte,word in codec.codebook.items():
            ids=tokenizer.encode(f' {byte:02X}',add_special_tokens=False)
            weights=torch.arange(1,len(ids)+1,dtype=torch.float32);weights/=weights.sum()
            value=(old[ids]*weights[:,None]).sum(0);frequency=(frequencies.get(byte,0)+1)/len(word)
            for symbol in word:rows[symbol]+=value*frequency;counts[symbol]+=frequency
        rows/=counts.clamp_min(1)[:,None];rows+=torch.randn_like(rows)*.002
        model.get_input_embeddings().weight[OLD_VOCAB:].copy_(rows)
        assert torch.equal(model.get_input_embeddings().weight[:OLD_VOCAB],old)
    model.tie_weights();assert model.get_input_embeddings().weight is model.get_output_embeddings().weight
    attach(model,'q4');replica,packed=packed_copy(model,out/'initial.mkqb','q4')
    errors=[]
    for name,parameter in reference.named_parameters():
        other=replica.get_parameter(name)
        if name=='model.embed_tokens.weight':other=other[:OLD_VOCAB]
        errors.append(float((parameter-other).abs().max()))
    assert max(errors)==0.,max(errors)
    save(model,tokenizer,out/'hf','q4')
    del reference,replica,old;gc.collect();model.to('cuda')
    course=Course(tokenizer);tests={};limits={}
    for context in [512,1024,2048]:
        for micro in [128,64,32,16]:
            try:
                torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
                rng=course.rng.getstate();counts=dict(course.counts);digest=course.plan_digest
                traces={}
                for mode in ['h32','hex']:
                    course.rng.setstate(rng);course.counts=collections.Counter(counts);course.plan_digest=digest
                    model.train();model.zero_grad(set_to_none=True)
                    ids,mask,labels,lm=course.batch(mode,context,micro,1501,'cuda')
                    with torch.autocast('cuda',dtype=torch.bfloat16):loss=compact_loss(model,ids,mask,labels,lm,torch.tensor(allowed_ids(mode),device='cuda'))
                    assert torch.isfinite(loss);loss.backward()
                    assert all(torch.isfinite(p.grad).all()for p in model.parameters()if p.grad is not None)
                    new_grad=float(model.get_input_embeddings().parametrizations.weight.original.grad[OLD_VOCAB:].norm())
                    if mode=='h32':assert new_grad>0
                    traces[mode]={'plan_digest':course.plan_digest,'counts':dict(course.counts),'loss':float(loss.detach()),
                      'new_rows_gradient_norm':new_grad,'sequence_length':ids.shape[1]}
                    del ids,mask,labels,lm,loss
                assert traces['hex']['plan_digest']==traces['h32']['plan_digest']
                assert traces['hex']['counts']==traces['h32']['counts']
                limits[str(context)]=micro;tests[str(context)]={'micro':micro,'peak_cuda_bytes':torch.cuda.max_memory_allocated(),'formats':traces};break
            except torch.OutOfMemoryError:
                model.zero_grad(set_to_none=True);gc.collect();torch.cuda.empty_cache()
                if micro==16:raise
        print(json.dumps({'context_preflight':context,**tests[str(context)]}),flush=True)
    model.zero_grad(set_to_none=True)
    manifest={'arm':a.arm,'frozen_sha256':sha(ROOT/'frozen.json'),'source_packet_sha256':sha(source/'model.mkqb'),
      'initial_master_sha256':sha(out/'hf/model.safetensors'),'initial_packet':packed,'old_dequantized_parameters_max_difference':max(errors),
      'old_russian_vocabulary':OLD_VOCAB,'new_input_vocabulary':len(tokenizer),'output_rows':{m:len(allowed_ids(m))for m in ['hex','h32']},
      'identical_initialization_for_hex_and_h32':True,'parameters':sum(p.numel()for p in model.parameters()),
      'micro_bounds':limits,'gpu_preflight':tests,'diagnostic_optimizer_updates_saved':0,
      'public_language_train_sha256':sha(BUILD/'native-mixed-v1/language/train.u16'),
      'public_language_validation_sha256':sha(BUILD/'native-mixed-v1/language/validation.u16'),
      'domain_documents_sha256':sha(BUILD/'training/domain-documents.jsonl')}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps(manifest),flush=True)


if __name__=='__main__':main()
