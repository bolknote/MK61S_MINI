"""Full-command study paths and immutable starting point."""
import hashlib
import json
from pathlib import Path

from tasks import BUILD
from semantic_common import INITIAL,INITIAL_PACKET,INITIAL_MASTER_SHA,INITIAL_PACKET_SHA
from codec_common import compact_head,OLD_VOCAB

ROOT=BUILD/'full-isa-v1'
ARMS=['full','protected']


def read(path):return [json.loads(x)for x in Path(path).read_text().splitlines()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def allowed():return json.loads((ROOT/'output-token-ids.json').read_text())


class HexProtocol:
    @staticmethod
    def encode_text(text):return text
    @staticmethod
    def decode_reply(text):return text,None


def task_prompt(task,observation=None,initial_code=None,*,prime=False):
    from full_isa_protocol import prompt
    result=prompt(task['task'],angle=task['angle'],initial_code=initial_code,observation=observation)
    return result+('<write>'if prime else'')


def target(code,*,prime=False):
    from full_isa_protocol import answer
    text=answer(code)
    return text[len('<write>'):]if prime else text
