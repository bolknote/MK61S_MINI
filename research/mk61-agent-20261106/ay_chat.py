"""Local Q4 proposal runner; generated formulas remain unconfirmed hypotheses."""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoTokenizer
from ay_runtime import render,goal_state
from ay_teacher import pool_for
from ay_codec import to_program
from ar_spec import infer,spec_text
from native_verify import verify_export
from aq_eval import generate
from ay_common import compact_head,output_ids
from full_isa_vm import FullVM
from ha_protocol import assemble,bytes_text


def propose(folder,task,angle='DEG',inputs=None):
    folder=Path(folder);manifest=json.loads((folder/'manifest.json').read_text());arm=manifest['output_arm']
    model,verified=verify_export(folder);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
    compact_head(model,output_ids(tokenizer));pool=pool_for(task)
    # Only angle is supplied by the harness, no semantic task answer is present.
    goal={'id':'local-user','task':task,'spec':{'angle':angle},'pool':pool,'public_inputs':[]}
    prompt=render(goal_state(goal),arm);generation=generate(model,tokenizer,[prompt],forced_action='write')[0]
    result={'arm':arm,'quantization':'Q4','task':task,'angle':angle,'request_understanding':'unconfirmed',
            'generation':generation,'export_verified':verified}
    if generation.get('codec_error'):return result
    try:
        program,spec=to_program(generation['body'],pool,angle,arm)
        if spec is None:
            try:spec=infer(program,pool,angle)
            except (ValueError,ArithmeticError):pass
        result.update(proposal_bytes=bytes_text(generation['body']),MK61_HEX=bytes_text(assemble(program,pool,'asm')),
                      declared_spec=spec,formula=spec_text(spec))
        if inputs is not None:
            actual,_=FullVM().execute(assemble(program,pool,'asm'),inputs,angle=angle,max_commands=128,max_frames=1024)
            result['actual']={'status':actual['status'],'X':actual['numeric']['X'],'memory':{k:v for k,v in actual['numeric'].items()if k.startswith('R')}}
    except (ValueError,ArithmeticError,RuntimeError)as error:result['error']=str(error)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--task',required=True)
    p.add_argument('--angle',choices=['DEG','RAD','GRAD'],default='DEG');p.add_argument('--inputs',help='JSON of supplied register values')
    args=p.parse_args();torch.set_num_threads(4)
    print(json.dumps(propose(args.model,args.task,args.angle,json.loads(args.inputs)if args.inputs else None),ensure_ascii=False,indent=2))
