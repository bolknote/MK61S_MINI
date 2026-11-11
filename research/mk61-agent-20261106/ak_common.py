"""Calibrate raw action decisions while keeping the Q4 program generator frozen."""
from tasks import BUILD
from aj_common import HERE,OLD,ACTIONS,ACTION_IDS,CORRECT_IDS,END,body_ids,output_ids,compact_head,public_task,read,write,sha
ROOT=BUILD/'done-risk-v1'
PARENT=BUILD/'completion-retention-v2'
PARENT=PARENT if(PARENT/'export/lr10-terminal/hf').exists()else PARENT/'server-results'
INITIAL=PARENT/'export/lr10-terminal/hf'
INITIAL_PACKET=PARENT/'export/lr10-terminal/model.mkqb'
ARMS=['done','actions']
PANELS=[('main','{split}.jsonl','{split}-seeds.jsonl'),('skills','{split}-skills.jsonl','{split}-skill-seeds.jsonl'),('completion','{split}.jsonl','{split}-completion-seeds.jsonl')]

