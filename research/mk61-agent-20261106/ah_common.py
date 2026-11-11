"""Balanced continuation with a verified frozen-policy retention teacher."""
from tasks import BUILD
from ag_common import HERE,OLD,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE
from ag_common import ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,public_task,read,write,sha
ROOT=BUILD/'retention-debug-v1'
PARENT=BUILD/'false-done-v1'
PARENT=PARENT if(PARENT/'export/balanced/hf').exists()else PARENT/'server-results'
START=PARENT/'balanced/best.safetensors'
START_PACKET=PARENT/'export/balanced/model.mkqb'
TEACHER=PARENT/'export/balanced/hf'
ARMS=['replay','distill']

