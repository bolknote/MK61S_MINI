"""Four unchanged model combinations; choose on development before closed."""
import time
import torch
from bw_common import ROOT,MODELS,ROUTES,read,write,check_frozen,output_ids,compact_head
from bw_eval import Cache,evaluate,select,paired_primary_checks,brief
from be_model import load
from bu_model import frozen_digest
from bs_resources import configure,headroom


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    assert not(ROOT/'preselected.json').exists();models={};tok=None
    for profile,folder in MODELS.items():
        m,t=load(folder,'cuda:0')
        if tok is not None:assert tok.get_vocab()==t.get_vocab()
        tok=t;compact_head(m,output_ids(tok));models[profile]=m
    before={k:frozen_digest(m)for k,m in models.items()};cache=Cache();development={};closed={}
    torch.cuda.reset_peak_memory_stats();start=time.monotonic()
    for route in ROUTES:
        status('retired_diagnostic',route=route)
        r=evaluate(models,tok,route,'diagnostic',policy,status,cache)
        write(ROOT/('diagnostic-'+route+'.json'),r)
    for route in ROUTES:
        status('development',route=route)
        r=evaluate(models,tok,route,'development',policy,status,cache);development[route]=r
        write(ROOT/('development-'+route+'.json'),r);print({'development':route,'result':brief(r)},flush=True)
        assert all(frozen_digest(m)==before[k]for k,m in models.items());check_frozen()
    assert paired_primary_checks(development)
    # Same weights, tasks and protocol must reproduce the previously completed UU baseline.
    expected=read(ROOT/'expected-development-UU.json')
    for panel in ['primary','own','wrong']:assert development['UU'][panel]['summary']==expected[panel]['summary'],panel
    choice=select(development);choice['unix']=time.time();write(ROOT/'preselected.json',choice)
    for route in ROUTES:
        status('closed',route=route)
        r=evaluate(models,tok,route,'closed',policy,status,cache);closed[route]=r
        write(ROOT/('closed-'+route+'.json'),r);print({'closed':route,'result':brief(r)},flush=True)
        assert all(frozen_digest(m)==before[k]for k,m in models.items());check_frozen()
    assert paired_primary_checks(closed)
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':0,'chosen':choice['chosen'],
        'all_model_parameters_unchanged':True,'digests':before,'paired_primary_checks':True,'closed_used_for_selection':False,
        'cache_hits':cache.hits,'cache_misses':cache.misses,'seconds':time.monotonic()-start,
        'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'unix':time.time()});status('complete')


if __name__=='__main__':main()
