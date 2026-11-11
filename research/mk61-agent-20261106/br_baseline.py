"""Post-selection held-out baseline, without any extra training or reselection."""
import torch
from br_common import ROOT,read,write,sha,check_frozen,output_ids,compact_head
from br_model import load
from br_eval import evaluate,brief


if __name__=='__main__':
    torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False
    check_frozen();assert(ROOT/'preselected.json').exists()
    model,tokenizer=load('small');compact_head(model,output_ids(tokenizer))
    summary={}
    for panel in ['wording','inputs','new_ast']:
        result=evaluate(model,tokenizer,panel);write(ROOT/('baseline-'+panel+'.json'),result);summary[panel]=brief(result)
        print({'panel':panel,'baseline':summary[panel]},flush=True)
    write(ROOT/'baseline-complete.json',{'complete':True,'optimizer_updates':0,'selection_changed':False,'summary':summary,
          'source_sha256':sha(__file__),'initial_Q4_sha256':sha(ROOT/'initial/small/model.mkqb')})
    check_frozen()
