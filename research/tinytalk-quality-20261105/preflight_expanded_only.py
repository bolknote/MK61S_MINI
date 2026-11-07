#!/usr/bin/env python3
"""Exercise partial training, weight decay and QAT saving; verify frozen packed bytes."""
import argparse
import json
from pathlib import Path
import re
import struct

from common import core,load_model,logps,qat_modules,quantize,decode,control_format_processor
from expanded_only import ExpandedOnly


def main():
    import torch
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',required=True)
    p.add_argument('--reference-packed',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--device',default='cpu')
    p.add_argument('--seed',type=int,default=931751)
    p.add_argument('--cuda-qat-graphs',action='store_true')
    args=p.parse_args()
    out=Path(args.output);assert not out.exists();out.mkdir(parents=True)
    model,tok,device=load_model(args)
    qat=qat_modules(model,cuda_graphs=args.cuda_qat_graphs);guard=ExpandedOnly(model);guard.verify()
    examples=[
        ('I want to grow a small plant. Name one.','<|tt_intent:suggest|> Try mint.'),
        ('Please wish me luck with my new drawing.','<|tt_intent:positive|> Good luck with your drawing!'),
        ('My toy is silver. What color is my toy?','<|tt_intent:remember_other|> Silver.'),
        ('My name is Jorin. What should you call me?','<|tt_intent:remember_user|> Jorin.'),
    ]
    types=getattr(model.config,'tinytalk_answer_type_token_ids',{})
    if types:
        examples=[(q,a.replace('|> ',f'|><|tt_type:{kind}|> ',1))
            for (q,a),kind in zip(examples,['plant','wish','color','name'])]
    say=getattr(model.config,'tinytalk_answer_focus_separator_id',None)
    if say is not None:
        examples=[(q,re.sub(r'(<\|tt_type:\w+\|>) ',lambda m:m[1]+' '+focus+'<|tt_say|> ',a,count=1))
                  for (q,a),focus in zip(examples,['mint','drawing','Silver','Jorin'])]
    emit_intent=getattr(model.config,'tinytalk_emit_intent_token',True)
    if not emit_intent:examples=[(q,re.sub(r'^<\|tt_intent:\w+\|>','',a))for q,a in examples]
    rows,skipped=core.encode_rows(tok,[{'id':f'partial-preflight:{i}','messages':[{'role':'user','content':q}],
        'target':a,'kind':'diagnostic'} for i,(q,a) in enumerate(examples)],128)
    assert len(rows)==4 and not skipped
    # Deliberately enable decay: restoration must still protect fixed slices.
    optimizer=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=3e-7,weight_decay=.01)
    losses=[]
    for step in range(12):
        model.train();optimizer.zero_grad(set_to_none=True)
        _,loss,_,_=logps(model,rows,tok,device,example_balanced=True)
        assert torch.isfinite(loss);loss.backward()
        norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.);assert torch.isfinite(norm)
        for group in optimizer.param_groups:group['lr']=3e-7*(step+1)
        optimizer.step();guard.restore();guard.verify();losses.append(float(loss.detach()))
        if step==5:
            quantize.save_qat_checkpoint(model,out/'midpoint',qat);tok.save_pretrained(out/'midpoint');guard.verify()
    quantize.save_qat_checkpoint(model,out/'trained',qat);tok.save_pretrained(out/'trained');guard.verify()
    plain,_,_=load_model(args,out/'trained');plain.eval().requires_grad_(False)
    metadata=quantize.export(plain,out/'model.ttq4',{'recipe':'Isolated partial-training preservation diagnostic'})
    def unpack(path):
        data=Path(path).read_bytes();size=struct.unpack_from('<I',data,8)[0]
        return data,json.loads(data[12:12+size]),(12+size+15)//16*16
    before,bmeta,bo=unpack(args.reference_packed);after,ameta,ao=unpack(out/'model.ttq4')
    targets={t['name']:t for t in ameta['tensors']};checked=0;active_changed=0
    for t in bmeta['tensors']:
        u=targets[t['name']];a=before[bo+t['offset']:bo+t['offset']+t['bytes']];b=after[ao+u['offset']:ao+u['offset']+u['bytes']]
        if t['name'].endswith('mlp.c_fc.weight'):
            size=guard.old*(t['padded_columns']//32)*18
            assert a[:size]==b[:size];checked+=size;active_changed+=a[size:]!=b[size:]
        elif t['name'].endswith('mlp.c_fc.bias'):
            size=guard.old*4;assert a[:size]==b[:size];checked+=size;active_changed+=a[size:]!=b[size:]
        elif t['name'].endswith('mlp.c_proj.weight'):
            stride=t['padded_columns']//32*18;size=guard.old//32*18
            for row in range(t['shape'][0]):
                assert a[row*stride:row*stride+size]==b[row*stride:row*stride+size];checked+=size
                active_changed+=a[row*stride+size:(row+1)*stride]!=b[row*stride+size:(row+1)*stride]
        elif t['name'].endswith('wte.weight') and types:
            n=model.config.tinytalk_answer_type_base_vocab_size*t['padded_columns']//32*18
            assert a[:n]==b[:n];checked+=n;active_changed+=a[n:]!=b[n:]
        elif t['name'].endswith('wte.control_flat'):
            assert a!=b;active_changed+=1
        else:
            assert a==b,t['name'];checked+=len(a)
    assert active_changed>0
    wire_check=None
    if types:
        quantize.restore(plain,out/'model.ttq4')
        cases=[{'id':f'wire:{i}','messages':[{'role':'user','content':q}]}for i,(q,_)in enumerate(examples)]
        replies=decode(plain,tok,cases,device)
        separator=tok.encode(' ',add_special_tokens=False)
        intents=list(plain.config.tinytalk_intent_token_ids.values());type_ids=list(types.values())
        for row in replies:
            ids=row['raw_token_ids'];assert ids[:len(separator)]==separator
            at=len(separator)
            if emit_intent:assert ids[at]in intents;at+=1
            assert ids[at]in type_ids;at+=1
            body=ids[at:];assert not any(t in intents+type_ids for t in body)
            if say is not None:
                assert body.count(say)==1
                boundary=body.index(say);assert 1<=boundary<=model.config.tinytalk_answer_focus_max_tokens
                assert row['answer_focus']==tok.decode(body[:boundary],skip_special_tokens=True).strip()
                body=body[boundary+1:]
                assert row['reply']==tok.decode(body,skip_special_tokens=True).strip()
            triples=[tuple(body[i:i+3])for i in range(len(body)-2)];assert len(triples)==len(set(triples))
        # A fact in the prompt remains copyable; only a repeated generated
        # trigram is blocked. These are independent behavioral test cases.
        prompt=[1,2,3,1,2];head=separator+([intents[0]]if emit_intent else[])+[type_ids[0]]
        processor=control_format_processor(plain,tok,len(prompt))
        body_head=head+([1,2,3,say] if say is not None else [])
        scores=processor(torch.tensor([prompt+body_head+[1,2]],device=device),torch.zeros(1,len(tok),device=device))
        assert torch.isfinite(scores[0,3])
        scores=processor(torch.tensor([prompt+body_head+[1,2,3,1,2]],device=device),torch.zeros(1,len(tok),device=device))
        assert not torch.isfinite(scores[0,3])
        wire_check={'probes':len(replies),'all_private_headers_valid':True,
            'intent_header_emitted':emit_intent,
            'prompt_facts_remain_copyable':True,'generated_trigram_loops_blocked':True}
        if say is not None:
            limit=plain.config.tinytalk_answer_focus_max_tokens
            scores=processor(torch.tensor([prompt+head+[1]*limit],device=device),torch.zeros(1,len(tok),device=device))
            assert torch.isfinite(scores[0,say]) and torch.isfinite(scores).sum()==1
            scores=processor(torch.tensor([prompt+head+[1]],device=device),torch.zeros(1,len(tok),device=device))
            assert not torch.isfinite(scores[0,tok.eos_token_id])
            wire_check.update(answer_keywords_excluded_from_public_reply=True,
                keyword_values_remain_copyable_in_speech=True,keyword_length_bound_enforced=True,
                no_eos_before_speech=True)
    report={**guard.summary(),'steps':12,'cuda_qat_graphs':args.cuda_qat_graphs,'weight_decay_deliberately_enabled':.01,'checkpoint_mid_training_verified':True,
        'frozen_packed_payload_bytes_identical':checked,'changed_active_segments':active_changed,
        'losses':losses,'source_sha256':core.digest(Path(args.model)/'model.safetensors'),
        'typed_wire_format_check':wire_check,
        'packed_sha256':metadata['file_sha256'],'quality_improvement_measured':False,'native_runtime_measured':False}
    core.save(out/'preflight.json',report);print(json.dumps(report),flush=True)


if __name__=='__main__':main()
