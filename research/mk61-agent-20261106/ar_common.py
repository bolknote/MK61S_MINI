"""Frozen, no-SGD specification/DONE diagnostic."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ROOT = REPO / '.build/mk61-agent-20261106/spec-diagnostic-v1'
MODEL = REPO / '.build/mk61-agent-20261106/step-debug-v2/export/full'
if not MODEL.exists():
    MODEL = REPO / '.build/mk61-agent-20261106/step-debug-v2/server-results/export/full'
MAX_TURNS = 12
TEACHER = 'Qwen/Qwen3.8-Flash-Next-FP8'
URL = 'http://127.0.0.1:18080/v1/chat/completions'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path); path.parent.mkdir(exist_ok=True, parents=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_frozen():
    frozen = read(ROOT/'frozen.json')
    for name, digest in frozen['sources'].items():
        assert sha(HERE/name) == digest, name
    assert sha(ROOT/'goals.json') == frozen['goals_sha256']
    assert sha(ROOT/'policy.json') == frozen['policy_sha256']
    assert sha(MODEL/'model.mkqb') == frozen['small_packet_sha256']
    assert sha(MODEL/'hf/model.safetensors') == frozen['small_master_sha256']
    return frozen
