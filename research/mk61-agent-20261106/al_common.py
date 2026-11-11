"""Goal/code crossed supervision with internal Q4 adapters."""
from tasks import BUILD
from ak_common import HERE, PARENT, INITIAL, INITIAL_PACKET
from ak_common import ACTIONS, ACTION_IDS, CORRECT_IDS, END, body_ids, output_ids, compact_head, public_task, read, write, sha
ROOT = BUILD / 'semantic-cross-v1'
PREVIOUS = BUILD / 'done-risk-v1'
PREVIOUS = PREVIOUS if (PREVIOUS / 'initial-fresh.json').exists() else PREVIOUS / 'server-results'
ARMS = ['late', 'all']
PANELS = [('main', '{split}.jsonl', '{split}-seeds.jsonl'),
    ('skills', '{split}-skills.jsonl', '{split}-skill-seeds.jsonl'),
    ('completion', '{split}.jsonl', '{split}-completion-seeds.jsonl')]
