"""One bounded actor-only Q4 evaluation worker; explicitly no gradient updates."""
import time
import torch
from by_common import ROOT,ACTOR,read,write,check_frozen,output_ids,compact_head
from by_eval import evaluate,Cache
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert policy['optimizer_updates']==0 and not(ROOT/'complete.json').exists()
    actor,tok=load(ACTOR,'cuda:0');compact_head(actor,output_ids(tok));before=frozen_digest(actor);cache=Cache()
    torch.cuda.reset_peak_memory_stats()
    for split in ['development','closed']:
        status('gold_cycle',split=split);result=evaluate(actor,tok,split,policy,status,cache)
        write(ROOT/(split+'-gold.json'),result)
        assert frozen_digest(actor)==before;check_frozen()
        print({'split':split,'summary':result['own']['summary']},flush=True)
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':0,'actor_digest':before,
        'actor_unchanged':True,'answer_supplied':True,'independent_solution_score':False,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'unix':time.time()});status('complete')


if __name__=='__main__':main()
