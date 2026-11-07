"""Frozen H32/HEX experiment paths and reversible model/tool boundary."""
import json
from pathlib import Path
import re

from byte_codec import Codec
from tasks import BUILD

ROOT=BUILD/'codec-qat-v1'
ARMS=['champion','small']
MODES=['hex','h32']
TAGS=[f'<h{i:02d}>'for i in range(32)]
OLD_VOCAB=8192


def read(path):return [json.loads(x)for x in Path(path).read_text().splitlines()]
def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Protocol:
    def __init__(self,mode,codebook):
        if mode not in MODES:raise ValueError(mode)
        self.mode=mode
        data=codebook.get('byte_to_symbols',codebook)
        self.codec=Codec({int(k,16)if isinstance(k,str)else k:tuple(v)for k,v in data.items()},32)

    def body(self,code):
        return ' '.join(f'{x:02X}'for x in code)if self.mode=='hex'else''.join(TAGS[s]for s in self.codec.encode(code))

    @staticmethod
    def hex_bytes(text):
        words=text.strip().split()
        if not words or any(re.fullmatch(r'[0-9A-Fa-f]{2}',x)is None for x in words):raise ValueError('Malformed HEX body')
        if len(words)>105:raise ValueError('Program too long')
        return [int(x,16)for x in words]

    def bytes(self,text):
        if self.mode=='hex':return self.hex_bytes(text)
        symbols=re.findall(r'<h(\d{2})>',text)
        if not symbols or re.sub(r'<h\d{2}>|\s+','',text):raise ValueError('Malformed H32 body')
        code=self.codec.decode([int(x)for x in symbols],105)
        if not code:raise ValueError('Empty H32 program')
        return code

    def encode_text(self,text):
        if self.mode=='hex':return text
        # Code fields are transformed; ordinary Russian and numerical values
        # remain untouched. Replies, current-code fields and trace opcodes all
        # use the same representation at the neural boundary.
        text=re.sub(r'<write>\s*([0-9A-Fa-f\s]+)\s*</write>',
          lambda m:'<write>'+self.body(self.hex_bytes(m.group(1)))+'</write>',text)
        text=re.sub(r'(?m)(Исправь код: )([0-9A-Fa-f ]+)(?=\n|$)',
          lambda m:m.group(1)+self.body(self.hex_bytes(m.group(2))),text)
        text=re.sub(r'(\b\d{2,3}:)([0-9A-Fa-f]{2})(?= X=)',
          lambda m:m.group(1)+self.body([int(m.group(2),16)]),text)
        return text.replace('HEX','H32')

    def decode_reply(self,raw):
        """Return canonical HEX for the unchanged real emulator controller."""
        def replace(m):return '<write>'+' '.join(f'{x:02X}'for x in self.bytes(m.group(1)))+'</write>'
        try:
            text=re.sub(r'<write>(.*?)</write>',replace,raw,flags=re.S)
            return text,None
        except ValueError as error:
            return re.sub(r'<write>.*?</write>','<invalid-write/>',raw,flags=re.S),str(error)


def protocol(mode):return Protocol(mode,json.loads((ROOT/'codebook-32.json').read_text()))


def compact_head(model,allowed):
    """Project selected rows only, preserving HF generation's global token IDs."""
    import types
    import torch
    import torch.nn.functional as F
    ids=torch.tensor(allowed,device=next(model.parameters()).device,dtype=torch.long)
    def forward(head,hidden):
        chosen=F.linear(hidden,head.weight.index_select(0,ids))
        logits=torch.full((*chosen.shape[:-1],head.weight.shape[0]),float('-inf'),dtype=chosen.dtype,device=chosen.device)
        return logits.index_copy_(-1,ids,chosen)
    model.lm_head.forward=types.MethodType(forward,model.lm_head)
    return model


def allowed_ids(mode):return json.loads((ROOT/f'output-{mode}.json').read_text())
