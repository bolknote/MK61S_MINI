"""A new round learned from all forty remaining false-DONE episodes."""
from tasks import BUILD
from af_common import HERE,OLD,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE
from af_common import ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,public_task,read,write,sha
ROOT=BUILD/'false-done-v1'
PARENT=BUILD/'finish-debug-v1'
PARENT=PARENT if(PARENT/'export/replay/hf').exists()else PARENT/'server-results'
START=PARENT/'replay/best.safetensors'
START_PACKET=PARENT/'export/replay/model.mkqb'
ARMS=['balanced','focused']

