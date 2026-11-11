"""Continue one shared semantic warmup while preserving the legacy state format."""
from am_common import HERE,PARENT,INITIAL,INITIAL_PACKET,ACTIONS,ACTION_IDS,CORRECT_IDS,END,OPS,BINDINGS
from am_common import read,write,sha,body_ids,output_ids,compact_head,public_task,labels
from am_common import ROOT as WARMUP
from tasks import BUILD
ROOT=BUILD/'hex-hypothesis-v2'
COMMON_CHECKPOINT=WARMUP/'direct/step-250.safetensors'
ARMS=['direct','planned']
PANELS=[('main','{split}.jsonl','{split}-seeds.jsonl'),('skills','{split}-skills.jsonl','{split}-skill-seeds.jsonl'),
 ('completion','{split}.jsonl','{split}-completion-seeds.jsonl')]
