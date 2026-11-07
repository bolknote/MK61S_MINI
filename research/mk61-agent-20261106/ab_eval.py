"""Same raw evaluation; a segmented primer and deterministic neural headers."""
import time
import torch
import torch.nn.functional as F
from transformers import LogitsProcessorList
import aa_eval as base
from ab_common import ROOT,INITIAL,INITIAL_PACKET,SOURCE,ACTIONS,ACTION_IDS,output_ids,CONTEXT
from ab_protocol import prompt_ids,header_ids,NO_BODY,END,Grammar,decode,as_xml
from ab_runtime import Session


class BodyGrammar:
    def __init__(self,tokenizer,start,action):self.start=start;self.action=action;self.grammar=Grammar(tokenizer,0)
    def __call__(self,ids,scores):
        out=torch.full_like(scores,-float('inf'))
        for i,values in enumerate(ids[:,self.start:].tolist()):
            if END in values:allowed=[END]
            else:
                text=''.join(self.grammar.pieces.get(v,'')for v in values)
                allowed=self.grammar.permitted(self.action,text)
            out[i,list(allowed)]=scores[i,list(allowed)]
        return out


def generate(model,tokenizer,prompts):
    prompts=[p if p.endswith('<')else p+'<'for p in prompts]
    encoded=[prompt_ids(tokenizer,p)for p in prompts];rows=[None]*len(prompts)
    valid=[i for i,p in enumerate(encoded)if len(p)<CONTEXT-8]
    for i in set(range(len(prompts)))-set(valid):
        rows[i]={'action':None,'body':[],'reply':'','raw_reply':'','codec_error':'context_overflow',
                 'generated_token_ids':[],'generated_tokens':0,'input_tokens':len(encoded[i])}
    if not valid:return rows
    device=next(model.parameters()).device;n=max(len(encoded[i])for i in valid)
    ids=torch.zeros((len(valid),n),dtype=torch.long,device=device);mask=torch.zeros_like(ids)
    for j,i in enumerate(valid):ids[j,:len(encoded[i])]=torch.tensor(encoded[i],device=device);mask[j,:len(encoded[i])]=1
    started=time.monotonic()
    with torch.inference_mode():
        hidden=model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
        selected=hidden[torch.arange(len(ids),device=device),mask.sum(1)-1]
        actions=F.linear(selected,model.get_input_embeddings().weight[ACTION_IDS]).argmax(-1).tolist()
    for act in sorted(set(actions)):
        action=ACTIONS[act];indexes=[i for j,i in enumerate(valid)if actions[j]==act]
        if action in NO_BODY:
            for i in indexes:rows[i]={'action':action,'body':[],'codec_error':None,'reply':as_xml(action,[])if action!='unsure'else'UNSURE',
                                      'generated_token_ids':[ACTION_IDS[act]],'generated_tokens':1,'input_tokens':len(encoded[i])}
            continue
        prefix=[encoded[i]+header_ids(tokenizer,action)for i in indexes];length=max(map(len,prefix))
        values=torch.zeros((len(prefix),length),dtype=torch.long,device=device);attention=torch.zeros_like(values)
        for j,p in enumerate(prefix):values[j,-len(p):]=torch.tensor(p,device=device);attention[j,-len(p):]=1
        with torch.inference_mode():
            out=model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(511,CONTEXT-length),do_sample=False,
                use_cache=True,pad_token_id=0,eos_token_id=END,logits_processor=LogitsProcessorList([BodyGrammar(tokenizer,length,action)]))
        for j,i in enumerate(indexes):
            tail=out[j,length:].tolist()
            if END in tail:tail=tail[:tail.index(END)]
            tokens=[ACTION_IDS[act],*tail]
            try:
                name,body=decode(tokenizer,tokens);error=None
                reply=as_xml(name,body)if name!='diag'else'DIAG '+' '.join(f'{b:02X}'for b in body)
            except ValueError as e:name=None;body=[];error=str(e);reply=''
            rows[i]={'action':name,'body':body,'reply':reply,'raw_reply':reply,'codec_error':error,'generated_token_ids':tokens,
                     'generated_tokens':len(tokens),'input_tokens':len(encoded[i]),'neural_header_tokens':len(header_ids(tokenizer,action)),
                     'batch_generation_seconds':time.monotonic()-started,'batch_size':len(indexes)}
    return rows


base.ROOT=ROOT;base.INITIAL=INITIAL;base.INITIAL_PACKET=INITIAL_PACKET;base.SOURCE=SOURCE
base.generate=generate;base.output_ids=output_ids
base.Session=Session
evaluate=base.evaluate;tool_panel=base.tool_panel;development=base.development;selection=base.selection


def brief(result):
    return {k:({n:v for n,v in r.items()if n not in ['details','by_opcode']}if isinstance(r,dict)else r)
            for k,r in result.items()}


base.brief=brief


if __name__=='__main__':base.main()
