"""Read-only pilot: preserve the old decoder prefix behind single-token actions.

Not a trained competitor, not used to select the action-alignment-v1 checkpoint.
The action is a wire/readout token; a deterministic header is inserted into KV.
No code or answer is synthesized by the adapter.
"""
import json
from pathlib import Path
import torch
import torch.nn.functional as F
from transformers import AutoTokenizer,AutoModelForCausalLM,LogitsProcessor,LogitsProcessorList
from aa_common import INITIAL,INITIAL_PACKET,SOURCE,ACTIONS,ACTION_IDS,body_ids,compact_head,write
from aa_protocol import Grammar,NO_BODY
from ha_protocol import parse_bytes,parse_call
from lowbit import load


class BodyGrammar(LogitsProcessor):
    def __init__(self,tokenizer,start,action):
        self.start=start;self.action=action;self.grammar=Grammar(tokenizer,0)
        self.grammar.eos=30
    def __call__(self,ids,scores):
        result=torch.full_like(scores,-float('inf'))
        for i,tail in enumerate(ids[:,self.start:].tolist()):
            if 30 in tail:allowed=[30]
            else:
                text=''.join(self.grammar.pieces.get(v,'')for v in tail)
                allowed=self.grammar.permitted(self.action,text)
            result[i,list(allowed)]=scores[i,list(allowed)]
        return result


class Bridge:
    def __init__(self,model,tokenizer):
        self.model=model;self.tokenizer=tokenizer;self.device=next(model.parameters()).device
        self.body_head=[i for i in body_ids(tokenizer)if i!=tokenizer.eos_token_id]+[30]
        self.headers={a:tokenizer.encode('<'+('patch'if a=='diag'else a)+'>',add_special_tokens=False)[1:]
                      for a in ['write','patch','run','diag']}
        compact_head(model,sorted(ACTION_IDS+self.body_head))

    def encode_prompt(self,prompt):
        assert prompt.endswith('<')
        return self.tokenizer.encode(prompt[:-1],add_special_tokens=False)+[30]

    def generate(self,prompts):
        encoded=[self.encode_prompt(p)for p in prompts];length=max(map(len,encoded));device=self.device
        ids=torch.zeros((len(encoded),length),dtype=torch.long,device=device);mask=torch.zeros_like(ids)
        for i,row in enumerate(encoded):ids[i,:len(row)]=torch.tensor(row,device=device);mask[i,:len(row)]=1
        with torch.inference_mode():
            hidden=self.model.model(input_ids=ids,attention_mask=mask,use_cache=False).last_hidden_state
            selected=hidden[torch.arange(len(ids),device=device),mask.sum(1)-1]
            acts=F.linear(selected,self.model.get_input_embeddings().weight[ACTION_IDS]).argmax(-1).tolist()
        rows=[None]*len(prompts)
        for act in sorted(set(acts)):
            action=ACTIONS[act];indexes=[i for i,a in enumerate(acts)if a==act]
            if action in NO_BODY:
                for i in indexes:rows[i]={'action':action,'body':[],'generated_token_ids':[ACTION_IDS[act]]}
                continue
            prefix=[encoded[i]+self.headers[action]for i in indexes];n=max(map(len,prefix))
            values=torch.zeros((len(prefix),n),dtype=torch.long,device=device);attention=torch.zeros_like(values)
            for j,row in enumerate(prefix):values[j,-len(row):]=torch.tensor(row,device=device);attention[j,-len(row):]=1
            with torch.inference_mode():
                output=self.model.generate(input_ids=values,attention_mask=attention,max_new_tokens=min(512,1024-n),
                    do_sample=False,use_cache=True,pad_token_id=0,eos_token_id=30,
                    logits_processor=LogitsProcessorList([BodyGrammar(self.tokenizer,n,action)]))
            for j,i in enumerate(indexes):
                tokens=output[j,n:].tolist()
                if 30 in tokens:tokens=tokens[:tokens.index(30)]
                try:body=parse_bytes(self.tokenizer.decode(tokens,clean_up_tokenization_spaces=False));error=None
                except ValueError as e:body=[];error=str(e)
                rows[i]={'action':action,'body':body,'generated_token_ids':[ACTION_IDS[act],*tokens],'error':error}
        return rows


def main():
    torch.set_num_threads(4);torch.manual_seed(715201)
    tokenizer=AutoTokenizer.from_pretrained(INITIAL,local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained(INITIAL,local_files_only=True);load(model,INITIAL_PACKET);model.eval()
    with torch.no_grad():
        w=model.get_input_embeddings().weight
        for new,letter in zip(ACTION_IDS,['w','p','r','t','t','d','u']):w[new].copy_(w[tokenizer.encode(letter,add_special_tokens=False)[0]])
    report=json.loads((SOURCE/'results/active-best.json').read_text())
    documented=[r for r in report['isa']['details']if r['kind']=='primitive'and r['catalog_risk']=='documented']
    chosen=documented[::20]+report['legacy']['details']
    engine=Bridge(model,tokenizer);rows=[]
    for at in range(0,len(chosen),16):
        batch=chosen[at:at+16]
        for old,new in zip(batch,engine.generate([r['prompt']+'<'for r in batch])):
            try:kind,expected=parse_call(old['reply']);same=new['action']==kind and new['body']==expected
            except ValueError:expected=None;same=False
            rows.append({'id':old['id'],'old_semantic_pass':old['pass'],'same_serialized_program':same,
                         'old_reply':old['reply'],'new':new})
    result={'no_SGD_updates':True,'not_used_for_v1_selection':True,'original_weight_rows_unchanged':True,
            'control_rows_only_initialized_from_existing_letters':True,'comparisons':len(rows),
            'exact_program_matches':sum(r['same_serialized_program']for r in rows),'details':rows,
            'segmented_primer_avoids_space_lt_BPE_merge':True,'body_header_is_original_token_sequence':True,
            'body_end_readout_is_original_lt_row_30':True,'physical_picocalc_measured':False}
    destination=HERE_ROOT=Path(__file__).resolve().parents[2]/'.build/mk61-agent-20261106/action-alignment-v1/header-pilot.json'
    write(destination,result);print(json.dumps({k:v for k,v in result.items()if k!='details'}),flush=True)


if __name__=='__main__':main()
