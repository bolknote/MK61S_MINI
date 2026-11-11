"""One program representation and unambiguous argument decoder headers."""
from aa_protocol import Grammar as BaseGrammar,as_xml
from ac_common import ACTIONS,ACTION_IDS,ACTION_ID,ID_ACTION,END
from ha_protocol import bytes_text,parse_bytes
NO_BODY={'trace','done','unsure'}


def prompt_ids(tokenizer,text):
    assert text.endswith('<')
    return tokenizer.encode(text[:-1],add_special_tokens=False)+[END]


def header_ids(tokenizer,action):
    if action not in ['write','run']:raise ValueError('No argument header')
    values=tokenizer.encode('<'+action+'>',add_special_tokens=False)
    assert values[0]==END
    return values[1:]


def target_ids(tokenizer,action,body):
    if action not in ACTIONS:raise ValueError('Unsupported action')
    return [ACTION_ID[action]]+([]if action in NO_BODY else tokenizer.encode(bytes_text(body),add_special_tokens=False)+[END])


def decode(tokenizer,values):
    if not values or values[0]not in ID_ACTION:raise ValueError('Missing active action')
    action=ID_ACTION[values[0]];tail=values[1:]
    if END in tail:tail=tail[:tail.index(END)]
    if action in NO_BODY:
        if tail:raise ValueError('Unexpected argument')
        return action,[]
    body=parse_bytes(tokenizer.decode(tail,clean_up_tokenization_spaces=False))
    if action=='run'and len(body)!=1:raise ValueError('RUN_LENGTH')
    return action,body


class Grammar(BaseGrammar):
    def __init__(self,tokenizer,start):
        super().__init__(tokenizer,start);self.eos=END
