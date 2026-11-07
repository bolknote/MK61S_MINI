"""Public-input-only interactive runner for the experimental action protocol."""
import argparse
import json
from pathlib import Path
from aa_runtime import Session
from ha_protocol import constants


def main():
    ap=argparse.ArgumentParser();ap.add_argument('question');ap.add_argument('--model',type=Path,required=True)
    ap.add_argument('--angle',choices=['RAD','DEG','GRAD'],required=True);ap.add_argument('--inputs',default='{}')
    ap.add_argument('--tests');ap.add_argument('--native',action='store_true');ap.add_argument('--turns',type=int,default=10)
    a=ap.parse_args();bank=json.loads(a.tests)if a.tests else[json.loads(a.inputs)]
    task={'id':'interactive','task':a.question,'angle':a.angle,'constants':constants(a.question),
          'public_tests':[{'segments':[{'inputs':x}]}for x in bank],'max_commands':128,'max_frames':1024}
    folder=a.model.resolve()
    if a.native:
        from aa_native import Native
        engine=Native(folder);generate=engine.generate
    else:
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        from lowbit import load
        from aa_common import compact_head,output_ids
        from aa_eval import generate as hf_generate
        torch.set_num_threads(4);model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True)
        load(model,folder/'model.mkqb');model.eval();tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True)
        compact_head(model,output_ids(tokenizer));generate=lambda text:hf_generate(model,tokenizer,[text])[0]
    s=Session(task,'asm',gate=True,max_turns=a.turns)
    for _ in range(a.turns):
        row=generate(s.request())
        if row['codec_error']:print(json.dumps(row,ensure_ascii=False));break
        s.apply_action(row['action'],row['body']);print(json.dumps(s.history[-1],ensure_ascii=False),flush=True)
        if s.finished or s.abstained:break
    print(json.dumps({'model_declared_done':s.finished,'model_abstained':s.abstained,'loop_stopped':s.finished or s.abstained,
                      'verified_task_success':None,'independent_verification_available':False,'body':s.body},ensure_ascii=False))


if __name__=='__main__':main()
