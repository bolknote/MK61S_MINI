"""Evaluation-only bridge for old XML RUN's integer case index."""
import json
import torch
import ac_eval
from ac_common import ROOT,read,write


def main():
    original=ac_eval.parse_call
    def legacy_parse(text,current=None):
        action,body=original(text,current)
        if action=='run':body=[0 if body is None else body]
        return action,body
    ac_eval.parse_call=legacy_parse
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.4);torch.backends.cuda.matmul.allow_tf32=False
    model,tokenizer=ac_eval.compiler_model();result={}
    for split in ['validation','fresh']if(ROOT/'preselected.json').exists()else['validation']:
        result[split]=ac_eval.tool_panel(model,tokenizer,read(ROOT/(split+'.jsonl')),read(ROOT/(split+'-seeds.jsonl')),legacy=True)[0]
    write(ROOT/'baseline.json',result)
    print(json.dumps({k:ac_eval.stats(v['details'])for k,v in result.items()}),flush=True)


if __name__=='__main__':main()
