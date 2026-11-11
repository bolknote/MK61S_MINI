"""Six existing wire actions, with a five-byte localized diagnosis."""
from aa_protocol import Grammar as Parent
from ac_protocol import prompt_ids
from ap_common import ACTIONS, ACTION_IDS, ACTION_ID, ID_ACTION, END
from ha_protocol import bytes_text, parse_bytes
NO_BODY = {'trace', 'done', 'unsure'}


def header_ids(tokenizer, action):
    assert action in ['write', 'run', 'diag']
    ids = tokenizer.encode('<' + action + '>', add_special_tokens=False)
    assert ids[0] == END
    return ids[1:]


def decode(tokenizer, values):
    if not values or values[0] not in ID_ACTION:
        raise ValueError('ACTION')
    action = ID_ACTION[values[0]]
    tail = values[1:]
    if END in tail:
        tail = tail[:tail.index(END)]
    if action in NO_BODY:
        if tail:
            raise ValueError('UNEXPECTED_BODY')
        return action, []
    body = parse_bytes(tokenizer.decode(tail, clean_up_tokenization_spaces=False))
    if action == 'run' and len(body) != 1:
        raise ValueError('RUN_LENGTH')
    if action == 'diag' and len(body) != 5:
        raise ValueError('DIAG_LENGTH')
    return action, body


class Grammar(Parent):
    def __init__(self, tokenizer, start=0):
        super().__init__(tokenizer, start)
        self.eos = END


class BodyGrammar:
    def __init__(self, tokenizer, start, action):
        self.start = start
        self.action = action
        self.grammar = Grammar(tokenizer)

    def __call__(self, ids, scores):
        import torch
        out = torch.full_like(scores, -float('inf'))
        for i, values in enumerate(ids[:, self.start:].tolist()):
            text = ''.join(self.grammar.pieces.get(v, '') for v in values)
            allowed = [END] if END in values else self.grammar.permitted(self.action, text)
            out[i, list(allowed)] = scores[i, list(allowed)]
        return out
