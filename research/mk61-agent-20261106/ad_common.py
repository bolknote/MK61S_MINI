"""Local inference-only statistics/harness experiment; previous rounds are immutable."""
from pathlib import Path
import hashlib
import json
from tasks import BUILD
HERE=Path(__file__).resolve().parent
ROOT=BUILD/'stats-harness-v1'
PREVIOUS=BUILD/'debug-adapter-v2/server-results'
MODEL=PREVIOUS/'export/sft'
PRIOR_ROOT=BUILD/'opcode-statistics-v1'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return [json.loads(s)for s in Path(path).read_text().splitlines()if s.strip()]
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def save(path,rows):Path(path).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in rows))
