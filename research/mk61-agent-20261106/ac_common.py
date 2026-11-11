"""Frozen compiler and a Q4-aware tool-only LoRA experiment."""
from aa_common import HERE,INITIAL,INITIAL_PACKET,SOURCE,read,write,sha,compact_head
from tasks import BUILD
ROOT=BUILD/'debug-adapter-v2'
ARMS=['sft','outcome']
ACTIONS=['write','run','trace','done','unsure']
ACTION_IDS=[8192,8194,8195,8197,8198]
ACTION_ID=dict(zip(ACTIONS,ACTION_IDS))
ID_ACTION=dict(zip(ACTION_IDS,ACTIONS))
END=30
CONTEXT=1024
MAX_TURNS=10


def body_ids(tokenizer):
    from aa_common import body_ids as old
    return sorted([i for i in old(tokenizer)if i!=tokenizer.eos_token_id]+[END])


def output_ids(tokenizer):return sorted(ACTION_IDS+body_ids(tokenizer))
