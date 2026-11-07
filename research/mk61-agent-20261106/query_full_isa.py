"""Try an exported Q4 student with the exact full-ISA prompt and output mask."""
import argparse
import json
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from full_isa_common import compact_head,sha
from full_isa_eval import generate
from full_isa_protocol import prompt,decode
from full_isa_vm import FullVM
from lowbit import load


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('question');ap.add_argument('--model',type=Path,required=True)
    ap.add_argument('--angle',choices=['RAD','DEG','GRAD'],required=True)
    ap.add_argument('--inputs',default='{}',help='JSON object with X/Y/Z/T/X1 and R0–RE')
    args=ap.parse_args();folder=args.model.resolve();manifest=json.loads((folder/'manifest.json').read_text())
    assert sha(folder/'model.mkqb')==manifest['packed_sha256']
    torch.set_num_threads(4)
    tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    load(model,folder/'model.mkqb');model.eval();compact_head(model,json.loads((folder/'output-token-ids.json').read_text()))
    reply=generate(model,tokenizer,[prompt(args.question,angle=args.angle)])[0]
    result={'question':args.question,'angle':args.angle,'reply':reply['reply'],'packet_sha256':manifest['packed_sha256']}
    try:
        code=decode(reply['reply']);state,_=FullVM().execute(code,json.loads(args.inputs),angle=args.angle)
        result.update(code=code,status=state['status'],X=state['raw']['X'],pc=state['pc'],registers={k:v for k,v in state['raw'].items()if k.startswith('R')})
    except (ValueError,RuntimeError,ArithmeticError)as error:result['error']=str(error)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
