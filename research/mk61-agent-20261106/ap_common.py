"""Matched full/short prompt training for a 3M Q4 diagnostic repair agent."""
from tasks import BUILD
from al_common import HERE, INITIAL, INITIAL_PACKET, public_task, read, write, sha, body_ids, compact_head
ROOT = BUILD / 'step-debug-v1'
PARENT = BUILD / 'error-recognizer-v1'
PARENT = PARENT if (PARENT / 'prepared.json').exists() else PARENT / 'server-results'
ARMS = ['full', 'short']
ACTIONS = ['write', 'run', 'trace', 'done', 'unsure', 'diag']
ACTION_IDS = [8192, 8194, 8195, 8197, 8198, 8196]
CORRECT_IDS = [8199, 8200]
ACTION_ID = dict(zip(ACTIONS, ACTION_IDS))
ID_ACTION = dict(zip(ACTION_IDS, ACTIONS))
END = 30
MAX_TURNS = 12
CLASSES = ['correct', 'operation', 'argument', 'order']
ERROR_CLASSES = ['operation', 'argument', 'order', 'correct']


def output_ids(tokenizer):
    return sorted(ACTION_IDS + body_ids(tokenizer))
