"""Supplementary legacy-format audit of every exported trained actor; no selection."""
import torch
from cb_common import ROOT,PARENT,read,write,sha,check_frozen,output_ids,compact_head
from cb_eval import Cache,evaluate
from be_model import load
from bs_resources import configure,headroom


def status(phase,**extra):write(ROOT/'extra-status.json',{'phase':phase,**extra})


def main():
    check_frozen();plan=read(ROOT/'extra-protocol.json');assert plan['source_sha256']==sha(__file__)
    assert read(ROOT/'controller-complete.json')['all_own_workers_joined']and not(ROOT/'extra-complete.json').exists()
    policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    translator,tok=load(PARENT,'cuda:0');compact_head(translator,output_ids(tok));cache=Cache();extra={}
    roles=read(ROOT/'audit-roles.json')
    for role,formats in roles['evaluated'].items():
        if role=='parent'or'original'in formats:continue
        model,t=load(ROOT/'export'/role,'cuda:0');assert t.get_vocab()==tok.get_vocab();compact_head(model,output_ids(tok));cache.actor_role='extra-'+role
        status('legacy_closed_audit',role=role)
        value=evaluate(model,translator,tok,'closed','original',policy,status,cache)
        value.update(supplementary_audit=True,used_for_checkpoint_selection=False)
        write(ROOT/f'closed-{role}-original.json',value);extra[role]=['original'];del model;torch.cuda.empty_cache()
    check_frozen();write(ROOT/'extra-complete.json',{'complete':True,'all_own_workers_joined':True,'optimizer_updates':0,
        'additional_formats':extra,'used_for_selection':False,'protocol_sha256':sha(ROOT/'extra-protocol.json')})
    print(read(ROOT/'extra-complete.json'),flush=True)


if __name__=='__main__':main()
