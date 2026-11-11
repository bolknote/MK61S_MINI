"""Semantic correctness supervision and paired higher-capacity tool training."""
from pathlib import Path
from tasks import BUILD
from ac_common import HERE,ACTIONS,ACTION_IDS,END,MAX_TURNS,body_ids,output_ids,compact_head
from aa_common import SOURCE as COMPILER_SOURCE,INITIAL as COMPILER,INITIAL_PACKET as COMPILER_PACKET
from full_isa_common import read,write,sha
ROOT=BUILD/'semantic-debug-v2'
OLD=BUILD/'debug-adapter-v2'
OLD=OLD if(OLD/'export/sft/hf').exists()else OLD/'server-results'
INITIAL=OLD/'export/sft/hf'
INITIAL_PACKET=OLD/'export/sft/model.mkqb'
ARMS=['lora16','full']
CORRECT_IDS=[8199,8200] # incorrect, correct; never input tokens or wire actions


def public_task(task):
    result={k:task[k]for k in ['id','task','angle','constants','max_commands','max_frames']if k in task}
    result['public_tests']=[{'segments':[{'inputs':dict(s['inputs'])}for s in c['segments']]}for c in task['public_tests']]
    return result
