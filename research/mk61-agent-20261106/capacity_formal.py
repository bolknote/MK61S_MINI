"""Run the complete old 98-task formal regression after selection is frozen."""
import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from evaluate import read_tasks
from evaluate_batched import evaluate
from lowbit import export,load
from quantization import export_q4,load_q4


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--tasks',type=Path,required=True)
    p.add_argument('--format',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    torch.set_num_threads(2);torch.cuda.set_per_process_memory_fraction(.025)
    model=AutoModelForCausalLM.from_pretrained(a.model,local_files_only=True,trust_remote_code=False).eval()
    tokenizer=AutoTokenizer.from_pretrained(a.model,local_files_only=True,trust_remote_code=False)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    path=a.output.with_suffix('.mkq4'if a.format=='q4'else'.mkqb')
    if a.format=='q4':packed=export_q4(model,path);load_q4(model,path)
    else:packed=export(model,path,a.format);load(model,path)
    result=evaluate(model.to('cuda'),tokenizer,read_tasks(a.tasks),plan=False,max_new=160,batch_size=24)
    result.update(model=str(a.model),format=a.format,packed=packed,selection_used_this_full_suite=False)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items()if k!='details'},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
