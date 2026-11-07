"""Wire action is not fed back as a novel input embedding."""
from aa_protocol import NO_BODY,from_xml,as_xml
from aa_protocol import Grammar as ParentGrammar
from aa_common import ACTIONS,ACTION_IDS,ACTION_ID
from ha_protocol import bytes_text,parse_bytes
END=30


def prompt_ids(tokenizer,prompt):
    assert prompt.endswith('<')
    # Preserve the old prompt boundary; ' <' is otherwise merged into ID5961.
    return tokenizer.encode(prompt[:-1],add_special_tokens=False)+[END]


def header_ids(tokenizer,action):
    tag='patch'if action=='diag'else action
    prefix=tokenizer.encode('<'+tag+'>',add_special_tokens=False)
    assert prefix[0]==END
    return prefix[1:]


def target_ids(tokenizer,action,body):
    return [ACTION_ID[action]]+([]if action in NO_BODY else tokenizer.encode(bytes_text(body),add_special_tokens=False)+[END])


class Grammar(ParentGrammar):
    def __init__(self,tokenizer,prefix_length):
        super().__init__(tokenizer,prefix_length)
        self.eos=END


def decode(tokenizer,values):
    if not values or values[0]not in ACTION_IDS:raise ValueError('Missing action')
    action=ACTIONS[ACTION_IDS.index(values[0])];values=values[1:]
    if END in values:values=values[:values.index(END)]
    if action in NO_BODY:
        if values:raise ValueError('Unexpected body')
        return action,[]
    body=parse_bytes(tokenizer.decode(values,clean_up_tokenization_spaces=False))
    if action=='run'and len(body)!=1:raise ValueError('RUN_LENGTH')
    if action=='diag'and len(body)!=5:raise ValueError('DIAG_LENGTH')
    if action=='patch'and len(body)<2:raise ValueError('PATCH_OFFSET')
    return action,body
