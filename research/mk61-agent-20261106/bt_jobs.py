"""One weight-frozen Q4 model, five diagnostic harnesses, then sealed audit."""
import time
import torch
from bt_common import ROOT,CONFIGS,read,write,check_frozen,compact_head,output_ids
from bs_model import parent
from bs_resources import configure,headroom
from bt_eval import evaluate,key,brief


def status(phase,**extra):write(ROOT/'status.json',{'phase':phase,'unix':time.time(),**extra})


def main():
    torch.set_num_threads(3);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    check_frozen();policy=read(ROOT/'policy.json');headroom(policy,status);configure(policy)
    model,tok=parent('cuda:0');model.eval();compact_head(model,output_ids(tok));reports={}
    assert not(ROOT/'preselected.json').exists(),'No duplicate audit'
    torch.cuda.reset_peak_memory_stats();started=time.monotonic()
    for name in policy['diagnostic_order']:
        status('diagnostic',config=name);report=evaluate(model,tok,'diagnostic',name,policy,status)
        write(ROOT/('diagnostic-'+name+'.json'),report);reports[name]=report
        print({'diagnostic':name,'summary':brief(report)},flush=True);check_frozen();torch.cuda.empty_cache()
    baseline=reports['baseline'];scores={};checks={}
    for name,r in reports.items():scores[name],checks[name]=key(r,baseline)
    selected='baseline'
    # Stable insertion order resolves ties in favor of baseline, then fewer changes.
    for name in CONFIGS:
        if scores[name][0]and scores[name]>scores[selected]:selected=name
    challenger=max([n for n in CONFIGS if n!='baseline'],key=lambda n:scores[n][1:])
    roles=list(dict.fromkeys(['baseline',selected,challenger]if selected=='baseline'else ['baseline',selected]))
    write(ROOT/'preselected.json',{'selected':selected,'challenger':challenger,'evaluated_closed':roles,
       'scores':scores,'checks':checks,'closed_seen':False,'unix':time.time(),'optimizer_updates':0})
    for name in roles:
        status('closed',config=name);r=evaluate(model,tok,'closed',name,policy,status)
        write(ROOT/('closed-'+name+'.json'),r);print({'closed':name,'summary':brief(r)},flush=True)
        check_frozen();torch.cuda.empty_cache()
    write(ROOT/'complete.json',{'complete':True,'all_audits_complete':True,'optimizer_updates':0,
       'selected':selected,'challenger':challenger,'closed_evaluated':roles,'closed_used_for_selection':False,
       'seconds':time.monotonic()-started,'peak_allocated_MiB':torch.cuda.max_memory_allocated()/2**20,
       'peak_reserved_MiB':torch.cuda.max_memory_reserved()/2**20,'unix':time.time()});status('complete')


if __name__=='__main__':main()
