"""Compact-state and on-policy intent correction, separate from frozen BJ/BK."""
from bj_common import HERE, REPO, read, write, rows, save_rows, sha, signature, ACTIONS, ACTION_IDS, CORRECT_IDS, END, MAX_TURNS, body_ids, output_ids, compact_head
import bj_common as previous

ROOT = REPO / '.build/mk61-agent-20261106/spec-compact-own-errors-v1'
PARENT = previous.ROOT if (previous.ROOT / 'export/fixed6000_full/model.mkqb').exists() else previous.ROOT / 'server-results'
SOURCES = {a: PARENT / 'export' / ('fixed6000_' + a) for a in ['lora', 'full']}
ARMS = ['lora', 'full']
PRIORS = list(dict.fromkeys([*previous.PRIORS, PARENT]))
DEV_NUMBERS = ['0.49713', '0.99713', '8.82713', '25.32713', '39.07713', '53.82713', '68.57713', '83.32713', '96.07713']
TEST_NUMBERS = ['0.55713', '1.05713', '11.82713', '27.32713', '43.07713', '56.82713', '71.57713', '88.32713', '97.07713']


def check_previous():
    previous.check_frozen()


def check_frozen():
    check_previous(); f = read(ROOT / 'frozen.json')
    for n, digest in f['sources'].items():
        assert sha(HERE / n) == digest, n
    for n, digest in f['files'].items():
        assert sha(ROOT / n) == digest, n
    for a, files in f['parents'].items():
        for n, digest in files.items():
            assert sha(SOURCES[a] / n) == digest, (a, n)
    return f
