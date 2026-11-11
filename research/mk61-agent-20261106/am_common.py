"""Explicit self-predicted HEX hypotheses with separate semantic diagnostics."""
from tasks import BUILD
from al_common import HERE, PARENT, INITIAL, INITIAL_PACKET
from al_common import ACTIONS, ACTION_IDS, CORRECT_IDS, END, body_ids, output_ids, compact_head, public_task, read, write, sha
ROOT = BUILD/'hex-hypothesis-v1'
SOURCE = BUILD/'semantic-cross-v1'
SOURCE = SOURCE if (SOURCE/'initial-fresh.json').exists() else SOURCE/'server-results'
ARMS = ['direct', 'planned']
PANELS = [('main', '{split}.jsonl', '{split}-seeds.jsonl'),
    ('skills', '{split}-skills.jsonl', '{split}-skill-seeds.jsonl'),
    ('completion', '{split}.jsonl', '{split}-completion-seeds.jsonl')]
OPS = ['identity', 'fourth', 'square', 'sqrt', 'sin', 'cos', 'tan', 'asin', 'acos', 'atan',
    'abs', 'neg', 'sign', 'int', 'frac', 'reciprocal', 'ln', 'log10', 'exp', 'pow10', '+', '-', '*', '/', 'other']
BINDINGS = 34


def labels(task, pool):
    from decimal import Decimal
    expr = task.get('expression')
    if expr is None: return [-1, -1]
    if isinstance(expr, list):
        op = 'fourth' if expr[0] == 'square' and isinstance(expr[1], list) and expr[1][0] == 'square' else expr[0]
        leaf = expr[1][1] if op == 'fourth' else expr[1]
        if len(expr) > 2: return [OPS.index(op) if op in OPS else 24, 32]
    else: op, leaf = 'identity', expr
    if isinstance(leaf, str):
        binding = 0 if task.get('source_kind') == 'X' else 1+int(leaf[1:], 16) if leaf.startswith('R') else 33
    elif isinstance(leaf, dict) and 'constant' in leaf:
        binding = next((16+i for i, v in enumerate(pool[:16]) if Decimal(v) == Decimal(str(leaf['constant']))), 33)
    else: binding = 33
    return [OPS.index(op) if op in OPS else 24, binding]
