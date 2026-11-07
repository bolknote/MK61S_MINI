"""Boundary correction, with original retention limits and a new sealed exam."""
import argparse
import json
import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

import ha_eval as base
from hr_common import ROOT,INITIAL,INITIAL_PACKET,ARMS,read,sha,write
from ha_common import allowed,compact_head


def development(model,tokenizer,strategy):
    previous=base.ROOT;base.ROOT=ROOT
    try:result=base.development(model,tokenizer,'asm')
    finally:base.ROOT=previous
    result['arm']=strategy;return result


def selection(result):
    previous=base.ROOT;base.ROOT=ROOT
    try:return base.selection(result)
    finally:base.ROOT=previous


def brief(result):
    previous=base.ROOT;base.ROOT=ROOT
    try:return base.brief(result)
    finally:base.ROOT=previous


def main():
    from native_quant import attach,packed_copy
    from lowbit import load
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=ARMS,required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists();base.ROOT=ROOT
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None)]
    if a.arm=='slow':paths.insert(0,('asm-baseline',INITIAL,INITIAL_PACKET))
    for label,path,source in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packet=ROOT/'results'/(label+'.mkqb');packet.parent.mkdir(exist_ok=True)
        if source:
            import shutil
            shutil.copyfile(source,packet);load(model,packet)
        else:attach(model,'q4');model,_=packed_copy(model,packet,'q4')
        model.to('cuda').eval();compact_head(model,allowed());base.audit(model,tokenizer,'asm',label,packet)
        result=json.loads((ROOT/'results'/(label+'.json')).read_text())
        result['observed_ablation']=base.evaluate(model,tokenizer,read(ROOT/'observed-ablation.jsonl'),'asm')
        result['strategy']='baseline'if source else a.arm;write(ROOT/'results'/(label+'.json'),result);del model


if __name__=='__main__':main()

