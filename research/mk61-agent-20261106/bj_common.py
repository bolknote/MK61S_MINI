"""Fresh intent/recovery course; previous BH exams are retired, never reused as tests."""
from bh_common import HERE, REPO, read, write, rows, save_rows, sha, signature, ACTIONS, ACTION_IDS, CORRECT_IDS, END, MAX_TURNS, body_ids, output_ids, compact_head
import bh_common as previous

ROOT = REPO / '.build/mk61-agent-20261106/spec-intent-recovery-v1'
PARENT = previous.ROOT if (previous.ROOT / 'export/fixed6000_lora/model.mkqb').exists() else previous.ROOT / 'server-results'
SOURCES = {a: PARENT / 'export' / ('fixed6000_' + a) for a in ['lora', 'full']}
ARMS = ['lora', 'full']
PRIORS = list(dict.fromkeys([*previous.PRIORS, previous.PARENT, PARENT]))
DEV_NUMBERS = ['0.465', '0.965', '8.635', '25.135', '38.885', '53.635', '68.385', '83.135', '95.885']
TEST_NUMBERS = ['0.515', '1.015', '11.635', '27.135', '42.885', '56.635', '71.385', '88.135', '96.885']


def check_frozen():
    previous.check_frozen()
    f = read(ROOT / 'frozen.json')
    for n, digest in f['sources'].items():
        assert sha(HERE / n) == digest, n
    for n, digest in f['files'].items():
        assert sha(ROOT / n) == digest, n
    for arm, files in f['parents'].items():
        for n, digest in files.items():
            assert sha(SOURCES[arm] / n) == digest, (arm, n)
    return f
