"""Matched semantic-spec/HEX distillation; all prior experiments remain frozen."""
import hashlib
import json
import os
from pathlib import Path
from ar_common import HERE, REPO, MODEL as INITIAL
from aq_common import ACTIONS, ACTION_IDS, CORRECT_IDS, END, MAX_TURNS, body_ids, compact_head, output_ids

ROOT=REPO/'.build/mk61-agent-20261106/semantic-spec-distill-v1'
ARMS=['hex','spec']
TEACHER='deepseek-ai/DeepSeek-V4.1-Flash'
URL='http://127.0.0.1:18081/v1/chat/completions'
DEV_EDGES=[('square','cos'),('sqrt','+'),('*','ln'),('+','frac'),('neg','ln'),('abs','-')]
TEST_EDGES=[('sin','square'),('cos','+'),('/','sqrt'),('-','sin'),('square','-'),('ln','abs')]


def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(x)for x in Path(path).read_text().splitlines()if x]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+f'.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def save_rows(path,values):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(json.dumps(v,ensure_ascii=False,separators=(',',':'))+'\n'for v in values))


def check_frozen():
    f=read(ROOT/'frozen.json')
    for n,d in f['sources'].items():assert sha(HERE/n)==d,n
    for n,d in f['files'].items():assert sha(ROOT/n)==d,n
    assert sha(INITIAL/'model.mkqb')==f['initial_packet_sha256']
    assert sha(INITIAL/'hf/model.safetensors')==f['initial_master_sha256']
    for n,d in f.get('initial_hf_files',{}).items():assert sha(INITIAL/'hf'/n)==d,n
    for n,d in f.get('external_sources',{}).items():assert sha(REPO/n)==d,n
    return f
