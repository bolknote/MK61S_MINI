"""Local Q4 proposal with optional arbitrary external constant-table order."""
import argparse
import json
from pathlib import Path
import torch
from transformers import AutoTokenizer
from native_verify import verify_export
from az_teacher import pool_for
from az_runtime import render,goal_state
from bb_canonical import request_state,response_body
from ay_common import compact_head,output_ids
from aq_eval import generate
from ay_codec import to_program
from ar_spec import spec_text
from full_isa_vm import FullVM
from ha_protocol import assemble,bytes_text


def propose(folder,task,angle='DEG',inputs=None,pool=None):
    folder=Path(folder);model,receipt=verify_export(folder);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
    compact_head(model,output_ids(tokenizer));pool=list(pool)if pool is not None else pool_for(task)
    goal={'id':'user-canonical','task':task,'spec':{'angle':angle},'pool':pool,'public_inputs':[]}
    actual=goal_state(goal);state=request_state(actual);prompt=render(state,'spec')
    generation=generate(model,tokenizer,[prompt],forced_action='write')[0]
    result={'task':task,'angle':angle,'quantization':'Q4','understanding':'unconfirmed','actual_pool':pool,'canonical_pool':state['pool'],
       'canonical_generation':generation,'export_verified':receipt,'order_policy':'canonical table, response indices remapped to external table'}
    if generation.get('codec_error'):return result
    try:
        body=response_body('write',generation['body'],actual);program,spec=to_program(body,pool,angle,'spec')
        result.update(proposal_bytes=bytes_text(body),MK61_HEX=bytes_text(assemble(program,pool,'asm')),declared_spec=spec,formula=spec_text(spec))
        if inputs is not None:
            value,_=FullVM().execute(assemble(program,pool,'asm'),inputs,angle=angle,max_commands=128,max_frames=1024)
            result['actual']={'status':value['status'],'X':value['numeric']['X']}
    except (ValueError,ArithmeticError,RuntimeError)as e:result['error']=str(e)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--task',required=True)
    p.add_argument('--angle',choices=['DEG','RAD','GRAD'],default='DEG');p.add_argument('--inputs');p.add_argument('--pool',help='JSON constant values in arbitrary order')
    a=p.parse_args();torch.set_num_threads(4)
    print(json.dumps(propose(a.model,a.task,a.angle,json.loads(a.inputs)if a.inputs else None,json.loads(a.pool)if a.pool else None),ensure_ascii=False,indent=2))
