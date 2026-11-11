"""One bounded A/B worker; all neural weights stay fixed."""
import time
import torch
from bz_common import ROOT,ACTOR,PARENT,read,write,check_frozen,output_ids,compact_head
from bz_eval import evaluate,selection,Cache
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert policy['optimizer_updates']==0 and not(ROOT/'complete.json').exists()
    actor,tok=load(ACTOR,'cuda:0');translator,t=load(PARENT,'cuda:0');assert tok.get_vocab()==t.get_vocab()
    for m in [actor,translator]:compact_head(m,output_ids(tok))
    before_actor=frozen_digest(actor);before_translator=frozen_digest(translator);cache=Cache();torch.cuda.reset_peak_memory_stats()
    for split in ['development','closed']:
        if split=='closed':assert(ROOT/'preselected.json').exists()
        reports={}
        for mode in ['gold','own']:
            status('compact_cycle',split=split,mode=mode);reports[mode]=evaluate(actor,translator,tok,split,mode,policy,status,cache)
            write(ROOT/(split+'-'+mode+'.json'),reports[mode])
            assert frozen_digest(actor)==before_actor and frozen_digest(translator)==before_translator;check_frozen()
            print({'split':split,'mode':mode,'summary':reports[mode]['own']['summary']},flush=True)
        if split=='development':
            choice=selection(reports,{m:read(ROOT/f'baseline-development-{m}.json')for m in ['gold','own']})
            write(ROOT/'preselected.json',{**choice,'unix':time.time()});print({'selection':choice},flush=True)
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':0,
        'actor_digest':before_actor,'translator_digest':before_translator,'actor_unchanged':True,'translator_unchanged':True,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'unix':time.time()});status('complete')


if __name__=='__main__':main()
