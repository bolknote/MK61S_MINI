"""Preserve the original neural HEX header behind the compact action wire."""
from aa_common import HERE,INITIAL,INITIAL_PACKET,SOURCE,ARMS,ACTIONS,ACTION_IDS,ACTION_ID,CONTEXT,MAX_TURNS,read,write,sha,compact_head
from aa_common import ROOT as PREVIOUS
from tasks import BUILD
ROOT=BUILD/'action-alignment-v2'
BASE=PREVIOUS


def body_ids(tokenizer):
    from aa_common import body_ids as original
    return sorted([i for i in original(tokenizer)if i!=tokenizer.eos_token_id]+[30])


def output_ids(tokenizer):return sorted(ACTION_IDS+body_ids(tokenizer))
