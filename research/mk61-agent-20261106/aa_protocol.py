"""Seven single-token actions; unchanged lossless HEX arguments."""
import re
from functools import lru_cache
import torch
from transformers import LogitsProcessor
from aa_common import ACTIONS, ACTION_IDS, ACTION_ID, body_ids
from ha_protocol import bytes_text, parse_bytes

NO_BODY = {'trace', 'done', 'unsure'}


def from_xml(reply):
    for action in ['trace', 'done']:
        if reply.strip() == f'<{action}/>': return action, []
    for action in ['write', 'patch', 'run']:
        found = re.match(r'<'+action+r'>(.*?)</'+action+r'>', reply, re.S)
        if found: return action, parse_bytes(found.group(1))
    raise ValueError('Unsupported historical target')


def as_xml(action, body):
    if action in ['trace', 'done']: return f'<{action}/>'
    if action == 'run': return f'<run>{bytes_text(body)}</run>'
    if action in ['write', 'patch']:
        return f'<{action}>{bytes_text(body)}</{action}><run/>'
    raise ValueError('Action has its own runtime handler')


def target_ids(tokenizer, action, body):
    values = [ACTION_ID[action]]
    if action not in NO_BODY:
        values += tokenizer.encode(bytes_text(body), add_special_tokens=False)
        values += [tokenizer.eos_token_id]
    return values


def decode(tokenizer, values):
    if not values or values[0] not in ACTION_IDS: raise ValueError('Missing action')
    action = ACTIONS[ACTION_IDS.index(values[0])]
    values = values[1:]
    if tokenizer.eos_token_id in values: values = values[:values.index(tokenizer.eos_token_id)]
    if action in NO_BODY:
        if values: raise ValueError('Unexpected arguments')
        return action, []
    body = parse_bytes(tokenizer.decode(values, clean_up_tokenization_spaces=False))
    if action == 'run' and len(body) != 1: raise ValueError('RUN requires one case index')
    if action == 'diag' and len(body) != 5: raise ValueError('DIAG requires five bytes')
    if action == 'patch' and len(body) < 2: raise ValueError('PATCH requires an offset')
    return action, body


class Grammar(LogitsProcessor):
    """Only syntax/length constraints: no instruction/answer lookup."""
    def __init__(self, tokenizer, prefix_length):
        self.start = prefix_length
        self.eos = tokenizer.eos_token_id
        self.pieces = {i: tokenizer.decode([i], clean_up_tokenization_spaces=False)
                       for i in body_ids(tokenizer) if i != self.eos}

    @lru_cache(maxsize=8192)
    def permitted(self, action, text):
        if action in NO_BODY: return (self.eos,)
        maximum = 1 if action == 'run' else 5 if action == 'diag' else 512
        minimum = 5 if action == 'diag' else 2 if action == 'patch' else 1
        result = []
        words = text.split(' ')
        if text and all(len(w) == 2 for w in words) and minimum <= len(words) <= maximum:
            result.append(self.eos)
        for token, piece in self.pieces.items():
            candidate = text + piece
            if not re.fullmatch(r'[0-9A-F]{1,2}( [0-9A-F]{0,2})*', candidate): continue
            parts = candidate.split(' ')
            if any(len(w) != 2 for w in parts[:-1]) or len(parts) > maximum: continue
            result.append(token)
        return tuple(result)

    def __call__(self, ids, scores):
        result = torch.full_like(scores, -float('inf'))
        for i, values in enumerate(ids[:, self.start:].tolist()):
            if not values: allowed = ACTION_IDS
            elif values[0] not in ACTION_IDS or self.eos in values: allowed = [self.eos]
            else:
                action = ACTIONS[ACTION_IDS.index(values[0])]
                text = ''.join(self.pieces.get(v, '') for v in values[1:])
                allowed = self.permitted(action, text)
            if not allowed: allowed = [self.eos]
            result[i, list(allowed)] = scores[i, list(allowed)]
        return result
