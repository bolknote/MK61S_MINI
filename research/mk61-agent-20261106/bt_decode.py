"""Single-episode bounded generation with actual persistent FP16/FP32 KV."""
import time
import torch
import torch.nn.functional as F
from transformers import LogitsProcessorList
from transformers.cache_utils import DynamicCache
from capacity_verify import FP16StorageCache
from aq_protocol import prompt_ids,header_ids,decode,NO_BODY,END,BodyGrammar
from aq_model import action_weight,correct_weight
from bt_common import ACTIONS,ACTION_IDS


def cache_stats(cache,config,half):
    tensors=[v for layer in cache.layers for v in [layer.keys,layer.values]if v is not None]
    dtype=torch.float16 if half else torch.float32
    assert all(v.dtype==dtype for v in tensors)
    stored=sum(v.numel()*v.element_size()for v in tensors);n=cache.get_seq_length()
    expected=n*2*config.num_hidden_layers*config.num_key_value_heads*config.head_dim*(2 if half else 4)
    assert stored==expected,(stored,expected)
    return {'bytes':stored,'tokens':n,'dtype':'FP16'if half else'FP32','attention_math':'FP32'}


@torch.inference_mode()
def one(model,tokenizer,prompt,context=1024,half=False,forced_action=None):
    started=time.monotonic();tokens=prompt_ids(tokenizer,prompt);n=len(tokens)
    assert not set(tokens)&set(ACTION_IDS)
    if n>=context-8:return {'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[],'input_tokens':n}
    device=next(model.parameters()).device;ids=torch.tensor([tokens],device=device)
    cache=(FP16StorageCache if half else DynamicCache)(config=model.config)
    h=model.model(input_ids=ids,attention_mask=torch.ones_like(ids),past_key_values=cache,use_cache=True).last_hidden_state[:,-1]
    act=int(F.linear(h,action_weight(model)).argmax(-1));margins=F.linear(h,correct_weight(model)).float()
    if forced_action:act=ACTIONS.index(forced_action)
    action=ACTIONS[act]
    if action in NO_BODY:result={'action':action,'body':[],'codec_error':None,'generated_token_ids':[ACTION_IDS[act]]}
    else:
        prefix=tokens+header_ids(tokenizer,action);length=len(prefix)
        if length>=context:return {'action':None,'body':[],'codec_error':'context_overflow','generated_token_ids':[],'input_tokens':n}
        values=torch.tensor([prefix],device=device)
        output=model.generate(input_ids=values,attention_mask=torch.ones_like(values),past_key_values=cache,
           max_new_tokens=min(511,context-length),do_sample=False,use_cache=True,pad_token_id=0,eos_token_id=END,
           logits_processor=LogitsProcessorList([BodyGrammar(tokenizer,length,action)]))
        tail=output[0,length:].tolist();ended=END in tail
        if ended:tail=tail[:tail.index(END)]
        generated=[ACTION_IDS[act],*tail]
        try:
            if not ended:raise ValueError('incomplete')
            a,b=decode(tokenizer,generated);error=None
        except ValueError as e:a=None;b=[];error=str(e)
        result={'action':a,'body':b,'codec_error':error,'generated_token_ids':generated}
    result.update(input_tokens=n,correctness_margin=float(margins[0,1]-margins[0,0]),
                  cache=cache_stats(cache,model.config,half),seconds=time.monotonic()-started,context=context)
    return result


def generate(model,tokenizer,prompts,config,forced_action=None):
    return [one(model,tokenizer,p,config['context'],config['KV']=='FP16',forced_action)for p in prompts]
