"""Public-input-only local runner for the trained semantic-debug profiles."""
import argparse
import json
from pathlib import Path
from ac_runtime import Session
from ha_protocol import constants,encode,assemble,parse_call


def main():
    ap=argparse.ArgumentParser();ap.add_argument('question');ap.add_argument('--root',type=Path,required=True)
    ap.add_argument('--arm',default='selected-research');ap.add_argument('--mode',choices=['raw','calibrated'],default='calibrated')
    ap.add_argument('--angle',choices=['RAD','DEG','GRAD'],required=True);ap.add_argument('--inputs',default='{}');ap.add_argument('--tests')
    ap.add_argument('--initial-hex');ap.add_argument('--native',action='store_true');a=ap.parse_args();root=a.root.resolve();folder=root/'export'/a.arm
    metadata=json.loads((folder/'protocol.json').read_text());threshold=metadata['correctness_threshold']if a.mode=='calibrated'else None
    bank=json.loads(a.tests)if a.tests else[json.loads(a.inputs)]
    task={'id':'interactive','task':a.question,'angle':a.angle,'constants':constants(a.question),
       'public_tests':[{'segments':[{'inputs':x}]}for x in bank],'max_commands':128,'max_frames':1024}
    if a.native:
        from ae_native import Engine
        engine=Engine(root,a.arm);tool=engine.generate
        from hf_runtime import prompt
        initial=lambda:engine.compile(prompt(task))
    else:
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        from ae_eval import generate
        from ae_common import output_ids,compact_head
        from lowbit import load
        torch.set_num_threads(4);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True);load(model,folder/'model.mkqb');model.eval();compact_head(model,output_ids(tokenizer))
        tool=lambda p:generate(model,tokenizer,[p])[0]
        compiler=AutoModelForCausalLM.from_pretrained(root/'export/compiler/hf',local_files_only=True);load(compiler,root/'export/compiler/model.mkqb');compiler.eval()
        compact_head(compiler,json.loads((root/'export/compiler/output-token-ids.json').read_text()))
        from hf_runtime import prompt
        from hf_eval import generate as old_generate
        def initial():
            g=old_generate(compiler,tokenizer,[prompt(task)])[0]
            try:act,body=parse_call(g['reply'])
            except ValueError:act=None;body=[]
            return {**g,'action':act,'body':body}
    s=Session(task,'asm',gate=threshold is not None);s.initial_history=0
    if a.initial_hex:s.body=encode(list(bytes.fromhex(a.initial_hex)),s.pool,'asm');s.run(0)
    else:
        g=initial()
        if g.get('codec_error')or g.get('action')!='write':print(json.dumps(g,ensure_ascii=False));return
        s.apply_action('write',g['body']);print(json.dumps(s.history[-1],ensure_ascii=False),flush=True)
    for _ in range(10-len(s.history)):
        g=tool(s.request())
        if g.get('codec_error'):print(json.dumps(g,ensure_ascii=False));break
        if g['action']=='done'and threshold is not None and s.eligibility()[0]and g['correctness_margin']<threshold:
            s.observation='Оценка решения не подтвердила соответствие условию. Проверь операцию, аргумент и требования задачи; при неуверенности выбери UNSURE.'
            s.history.append({'kind':'semantic_DONE_rejected','margin':g['correctness_margin'],'observation':s.observation});print(json.dumps(s.history[-1],ensure_ascii=False),flush=True);continue
        s.apply_action(g['action'],g['body']);print(json.dumps(s.history[-1],ensure_ascii=False),flush=True)
        if s.finished or s.abstained:break
    try:code=assemble(s.body,s.pool,'asm')if s.body else None
    except ValueError:code=None
    print(json.dumps({'mode':a.mode,'model_declared_done':s.finished,'model_abstained':s.abstained,'program':code,
       'verified_task_success':None,'trusted_expected_result_supplied':False,'physical_device_used':False},ensure_ascii=False))


if __name__=='__main__':main()
