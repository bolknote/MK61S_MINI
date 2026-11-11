"""Continue the terminal distill profile with complementary verified teachers."""
from tasks import BUILD
from ah_common import HERE,OLD,INITIAL,INITIAL_PACKET,COMPILER,COMPILER_PACKET,COMPILER_SOURCE
from ah_common import ACTIONS,ACTION_IDS,CORRECT_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head,public_task,read,write,sha
from ah_common import PARENT as PREVIOUS
ROOT=BUILD/'completion-retention-v1'
PARENT=BUILD/'retention-debug-v1'
PARENT=PARENT if(PARENT/'export/distill-terminal/hf').exists()else PARENT/'server-results'
START=PARENT/'distill/last.safetensors'
START_PACKET=PARENT/'export/distill-terminal/model.mkqb'
TEACHERS={'distill':(PARENT/'export/distill-terminal/hf',START_PACKET),
          'balanced':(PREVIOUS/'export/balanced/hf',PREVIOUS/'export/balanced/model.mkqb')}
ARMS=['lr20','lr10']
PANELS=[('main','{split}.jsonl','{split}-seeds.jsonl'),('skills','{split}-skills.jsonl','{split}-skill-seeds.jsonl'),
        ('goals','{split}-goals.jsonl','{split}-goal-seeds.jsonl'),('completion','{split}.jsonl','{split}-completion-seeds.jsonl')]

