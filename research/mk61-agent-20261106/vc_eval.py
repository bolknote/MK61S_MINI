import argparse
import json
import shutil
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer
from vc_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,read,write,sha
from vc_train import scores,metrics
from native_quant import attach,packed_copy
from lowbit import load


def main():
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=ARMS,required=True);a=p.parse_args()
    assert(ROOT/'preselected.json').exists();torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    head=torch.tensor(json.loads((ROOT/'output-token-ids.json').read_text()),device='cuda')
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None)]
    if a.arm=='slow':paths.insert(0,('baseline',INITIAL,INITIAL_PACKET))
    for label,path,source in paths:
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False);tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source:shutil.copyfile(source,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();val=scores(model,tokenizer,read(ROOT/'validation.jsonl'),head);v=metrics(val)
        fresh=scores(model,tokenizer,read(ROOT/'fresh.jsonl'),head);f=metrics(fresh,v['threshold'])
        result={'label':label,'packed_sha256':sha(packet),'validation':v,'fresh':f,'details':fresh,
                'validation_details':val,'fresh_used_for_selection':False,'oracle_values_in_runtime_input':False}
        write(ROOT/'results'/(label+'.json'),result);print(json.dumps({k:x for k,x in result.items()if k not in ['details','validation_details']}),flush=True);del model


if __name__=='__main__':main()
