"""Isolated action-supervision experiment. Historical rounds stay immutable."""
from pathlib import Path
from tasks import BUILD
from ha_common import read, write, sha, compact_head

HERE = Path(__file__).resolve().parent
ROOT = BUILD / 'action-alignment-v1'
BASE = BUILD / 'harness-debug-v3'
SOURCE = BASE if (BASE/'export/selected-budget/hf').exists() else BASE/'server-results'
INITIAL = SOURCE/'export/selected-budget/hf'
INITIAL_PACKET = SOURCE/'export/selected-budget/model.mkqb'
ARMS = ['sft', 'preference']
ACTIONS = ['write', 'patch', 'run', 'trace', 'diag', 'done', 'unsure']
ACTION_IDS = list(range(8192, 8199))
ACTION_ID = dict(zip(ACTIONS, ACTION_IDS))
CONTEXT = 1024
MAX_TURNS = 10


def body_ids(tokenizer):
    result = set()
    for i in range(256):
        for text in [f'{i:02X}', f' {i:02X}', f'{i:02X} ']:
            result.update(tokenizer.encode(text, add_special_tokens=False))
    return sorted(result | {tokenizer.eos_token_id})


def output_ids(tokenizer):
    return sorted(ACTION_IDS + body_ids(tokenizer))
