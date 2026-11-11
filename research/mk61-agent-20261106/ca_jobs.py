"""Compare three individual sections on development, then audit one frozen choice."""
import time
import torch
from ca_common import ROOT,ACTOR,PARENT,VARIANTS,read,write,check_frozen,output_ids,compact_head
from ca_eval import Cache,evaluate,choose
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert policy['optimizer_updates']==0 and not(ROOT/'complete.json').exists()
    actor,tok=load(ACTOR,'cuda:0');translator,t=load(PARENT,'cuda:0');assert tok.get_vocab()==t.get_vocab()
    for model in [actor,translator]:compact_head(model,output_ids(tok))
    before_actor=frozen_digest(actor);before_translator=frozen_digest(translator);cache=Cache();torch.cuda.reset_peak_memory_stats();reports={};evaluated=[]
    for variant in VARIANTS:
        reports[variant]={}
        for mode in ['gold','own']:
            status('part_cycle',split='development',mode=mode,variant=variant)
            value=evaluate(actor,translator,tok,'development',mode,variant,policy,status,cache)
            reports[variant][mode]=value;name=f'development-{variant}-{mode}.json';write(ROOT/name,value);evaluated.append(name)
            assert frozen_digest(actor)==before_actor and frozen_digest(translator)==before_translator;check_frozen()
            print({'variant':variant,'split':'development','mode':mode,'summary':value['own']['summary']},flush=True)
    parents={mode:read(ROOT/f'baseline-development-{mode}.json')for mode in ['gold','own']}
    selection=choose(reports,parents,read(ROOT/'CPU-preflight.json')['tokens_saved'])
    write(ROOT/'preselected.json',{**selection,'unix':time.time()});print({'selection':selection},flush=True)
    variant=selection['audit_variant']
    for mode in ['gold','own']:
        status('part_cycle',split='closed',mode=mode,variant=variant)
        value=evaluate(actor,translator,tok,'closed',mode,variant,policy,status,cache)
        name=f'closed-{variant}-{mode}.json';write(ROOT/name,value);evaluated.append(name)
        assert frozen_digest(actor)==before_actor and frozen_digest(translator)==before_translator;check_frozen()
        print({'variant':variant,'split':'closed','mode':mode,'summary':value['own']['summary']},flush=True)
    write(ROOT/'audit-roles.json',{'evaluated':evaluated,'audit_variant':variant,'selected_format':selection['chosen_format']})
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':0,'actor_digest':before_actor,
        'translator_digest':before_translator,'actor_unchanged':True,'translator_unchanged':True,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'unix':time.time()});status('complete')


if __name__=='__main__':main()
