"""An optional bounded harness grammar; it never receives an answer expression.

The coverage rule is deliberately an experimental assumption: every register
mentioned in a short arithmetic condition is relevant. It is not a general
rule for calculator programs or instructions mentioning preserved memory.
"""
from dataclasses import dataclass, replace
from functools import lru_cache

ARITY={'+':2,'-':2,'*':2,'/':2,'abs':1,'neg':1,'square':1}


@dataclass(frozen=True)
class State:
    phase:str='start'
    pending:str=''
    slots:int=1
    operations:int=0
    seen:frozenset=frozenset()


class Grammar:
    def __init__(self,registers,max_operations=3):
        self.registers=frozenset(registers)
        if not self.registers or not self.registers<=frozenset(['R0','R1','R2','R3']):raise ValueError('Unsupported register set')
        self.max_operations=max_operations
        self.terminals=tuple(ARITY)+tuple(sorted(self.registers))

    def viable(self,state):
        if state.operations>self.max_operations or state.slots<0:return False
        missing=len(self.registers-state.seen)
        if state.slots==0:return missing==0 and state.operations>0
        return missing<=state.slots+self.max_operations-state.operations

    def completed_terminal(self,state,token):
        arity=ARITY.get(token,0)
        return replace(state,phase='separator',pending='',slots=state.slots-1+arity,
          operations=state.operations+(token in ARITY),seen=state.seen|({token}if not arity else set()))

    @lru_cache(maxsize=32768)
    def advance(self,state,text):
        for char in text:
            if state.phase=='done':return state
            if state.phase in ['start','close']:
                target='<calc>'if state.phase=='start'else'</calc>'
                pending=state.pending+char
                if not target.startswith(pending):return None
                state=replace(state,pending=pending)
                if pending==target:state=replace(state,phase='token'if state.phase=='start'else'done',pending='')
                continue
            if state.phase=='separator':
                if char.isspace():state=replace(state,phase='token');continue
                if state.slots==0 and char=='<':state=replace(state,phase='close',pending='<');continue
                return None
            if not state.pending and char.isspace():continue
            if not state.pending and state.slots==0:
                if char!='<':return None
                state=replace(state,phase='close',pending='<');continue
            pending=state.pending+char
            # A partial BPE token must retain a viable completed terminal.
            # Otherwise e.g. "a" could enter "abs" after the operation budget.
            options=[x for x in self.terminals if x.startswith(pending)and self.viable(self.completed_terminal(state,x))]
            if not options:return None
            if pending in options:
                state=self.completed_terminal(state,pending)
            else:state=replace(state,pending=pending)
        return state


def processor(tokenizer,register_sets,prompt_length,max_operations=3):
    # Importing the pure state machine above does not require a torch runtime.
    import torch
    from transformers import LogitsProcessor

    class Constraint(LogitsProcessor):
        def __init__(self):
            self.grammars=[Grammar(rs,max_operations)for rs in register_sets]
            self.vocabulary=[tokenizer.decode([i],skip_special_tokens=False,clean_up_tokenization_spaces=False)for i in range(len(tokenizer))]
            self.allowed={}
            self.prefixes={}

        def __call__(self,input_ids,scores):
            for i,row in enumerate(input_ids):
                grammar=self.grammars[i];tokens=tuple(row[prompt_length:].tolist());key=(i,tokens)
                if key not in self.prefixes:
                    if tokens and(i,tokens[:-1])in self.prefixes:
                        state=grammar.advance(self.prefixes[(i,tokens[:-1])],self.vocabulary[tokens[-1]])
                    else:
                        state=State()
                        for token in tokens:
                            state=grammar.advance(state,self.vocabulary[token])
                            if state is None:break
                    self.prefixes[key]=state
                state=self.prefixes[key]
                if state is None:raise ValueError('Generation escaped the bounded grammar')
                if state.phase=='done':continue
                cache=(grammar.registers,state)
                if cache not in self.allowed:
                    self.allowed[cache]=[j for j,text in enumerate(self.vocabulary)if text and j!=tokenizer.eos_token_id and grammar.advance(state,text)is not None]
                allowed=self.allowed[cache]
                if not allowed:raise ValueError('No possible continuation in bounded grammar: '+repr(state))
                blocked=torch.full_like(scores[i],float('-inf'));blocked[allowed]=scores[i,allowed];scores[i]=blocked
            return scores
    return Constraint()
