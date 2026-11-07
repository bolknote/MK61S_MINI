"""Fresh language evaluation with full-ISA regression kept separate."""
import argparse
import collections
import json

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from natural_common import ROOT,INITIAL,INITIAL_PACKET,read,sha,write,allowed,compact_head
from full_isa_eval import evaluate,old_formal,tools,development as old_development
from codec_eval import language_nll


def development(model,tokenizer):
    previous=old_development(model,tokenizer)
    previous['natural']=evaluate(model,tokenizer,read(ROOT/'validation-language.jsonl'))
    return previous


def selection(result):
    doc=result['panel']['documented_instructions']['rate'];language=result['natural'];legacy=result['legacy']['rate']
    groups=language['by_group'];macro=sum(x['rate']for x in groups.values())/len(groups)
    control=result['panel']['by_kind']['programming']['rate']
    return [doc>=.99,.65*macro+.15*doc+.1*control+.1*legacy,macro,doc,control,legacy]


def brief(result):
    return {'key':selection(result),'documented':result['panel']['documented_instructions'],
      'kinds':result['panel']['by_kind'],'groups':result['panel']['by_group'],
      'natural':{k:v for k,v in result['natural'].items()if k!='details'},
      'legacy':{k:result['legacy'][k]for k in ['passed','total','rate']}}


def main():
    from lowbit import load
    from native_quant import attach,packed_copy
    ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['full','protected'],required=True);a=ap.parse_args()
    assert(ROOT/'preselected.json').exists()
    torch.set_num_threads(4);torch.cuda.set_per_process_memory_fraction(.2)
    paths=[(a.arm+'-best',ROOT/a.arm/'best',None),(a.arm+'-endpoint',ROOT/a.arm/'last',None)]
    if a.arm=='full':paths.insert(0,('baseline',INITIAL,INITIAL_PACKET))
    for label,path,source in paths:
        if(ROOT/'results'/(label+'.json')).exists():continue
        model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        tokenizer=AutoTokenizer.from_pretrained(path,local_files_only=True,trust_remote_code=False)
        packed=ROOT/'results'/(label+'.mkqb');packed.parent.mkdir(exist_ok=True)
        if source:
            import shutil
            shutil.copyfile(source,packed);load(model,packed)
        else:attach(model,'q4');model,_=packed_copy(model,packed,'q4')
        model.to('cuda').eval();compact_head(model,allowed())
        main_result=evaluate(model,tokenizer,read(ROOT/'audit.jsonl'))
        natural=evaluate(model,tokenizer,read(ROOT/'fresh-language.jsonl'))
        observed=evaluate(model,tokenizer,read(ROOT/'closed-natural.jsonl'))
        user=evaluate(model,tokenizer,read(ROOT/'observed-user-reproductions.jsonl'))
        legacy=old_formal(model,tokenizer);lookup={r['id']:r for r in natural['details']}
        ids=set(json.loads((ROOT/'tool-probe-ids.json').read_text()))
        tool=tools(model,tokenizer,[t for t in read(ROOT/'fresh-language.jsonl')if t['id']in ids],lookup)
        result={'label':label,'packed_sha256':sha(packed),'main':main_result,'natural':natural,
          'previous_natural_observed_retest':observed,'observed_user_reproductions':user,'legacy':legacy,'tools':tool,
          'language':language_nll(model),'new_audit_used_for_selection':False,'old_isa_exam_is_observed_regression':True,
          'previous_natural_153_is_observed_regression':True,'physical_picocalc_measured':False}
        write(ROOT/'results'/(label+'.json'),result)
        print(json.dumps({'label':label,'doc':main_result['documented_instructions'],'fresh':[natural['passed'],natural['total']],
          'groups':natural['by_group'],'observed153':[observed['passed'],observed['total']],
          'user':[user['passed'],user['total']],'legacy':legacy['passed'],'tools':tool['passed']}),flush=True)
        del model


if __name__=='__main__':main()

