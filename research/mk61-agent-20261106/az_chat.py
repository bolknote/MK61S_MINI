"""Q4 proposals with the new literal pool; formulas are still hypotheses."""
import argparse
import json
from pathlib import Path
import torch
import ay_chat as base
from az_teacher import pool_for

base.pool_for=pool_for
propose=base.propose


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--task',required=True)
    p.add_argument('--angle',choices=['DEG','RAD','GRAD'],default='DEG');p.add_argument('--inputs')
    a=p.parse_args();torch.set_num_threads(4)
    print(json.dumps(propose(a.model,a.task,a.angle,json.loads(a.inputs)if a.inputs else None),ensure_ascii=False,indent=2))
