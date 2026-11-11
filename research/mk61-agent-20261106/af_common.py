"""Continue the selected rank16 adapter on completion and semantic near misses."""
from pathlib import Path
from tasks import BUILD
from ae_common import HERE,OLD,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE
from ae_common import ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,public_task
from full_isa_common import read,write,sha

ROOT=BUILD/'finish-debug-v1'
PARENT=BUILD/'semantic-debug-v2'
PARENT=PARENT if(PARENT/'export/lora16/hf').exists()else PARENT/'server-results'
START=PARENT/'lora16/best.safetensors'
START_PACKET=PARENT/'export/lora16/model.mkqb'
ARMS=['replay','contrast']

