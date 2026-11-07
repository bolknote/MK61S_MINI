"""Run the local student / emulator tool loop, including native MKA inference."""
import argparse
import ctypes as C
import json
from pathlib import Path

from ha_protocol import constants,assemble
from hf_runtime import Session
from full_isa_vm import FullVM


class Native:
    def __init__(self,folder):
        library=folder.parent.parent/'native/codec-probe.dylib'
        self.lib=C.CDLL(str(library));l=self.lib
        l.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];l.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
        l.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
        l.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
        l.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
        self.buffer=C.create_string_buffer((folder/'model.mka').read_bytes());assert l.mk_ai_open(self.buffer,len(self.buffer)-1)==0
        ids=json.loads((folder/'output-token-ids.json').read_text());head=(C.c_ushort*len(ids))(*ids);l.codec_set_mask(head,len(ids))
        self.eos=json.loads((folder/'hf/generation_config.json').read_text()).get('eos_token_id',2)
        if isinstance(self.eos,list):self.eos=self.eos[0]

    def generate(self,text):
        l=self.lib;encoded=(C.c_ushort*1024)();used=C.c_uint();best=C.c_ushort()
        if l.codec_encode(text.encode(),encoded,1024,C.byref(used))!=0 or used.value>=1024:raise ValueError('Context overflow')
        l.mk_ai_reset()
        for i,token in enumerate(encoded[:used.value]):assert l.codec_forward(token,int(i+1==used.value),C.byref(best),None)==0
        parts=[];raw=C.create_string_buffer(128);count=C.c_uint()
        for _ in range(min(512,1024-used.value)):
            token=best.value
            if token==self.eos:break
            assert l.mk_ai_decode(token,raw,len(raw),C.byref(count))==0;parts.append(raw.raw[:count.value])
            assert l.codec_forward(token,1,C.byref(best),None)==0
        return b''.join(parts).decode()


def main():
    ap=argparse.ArgumentParser();ap.add_argument('question');ap.add_argument('--model',type=Path,required=True)
    ap.add_argument('--angle',choices=['RAD','DEG','GRAD'],required=True);ap.add_argument('--inputs',default='{}')
    ap.add_argument('--tests',help='Optional JSON array of input objects; contains no expected outputs')
    ap.add_argument('--native',action='store_true');ap.add_argument('--turns',type=int,default=6);a=ap.parse_args()
    folder=a.model.resolve();manifest=json.loads((folder/'manifest.json').read_text());arm=manifest['arm']
    values=json.loads(a.inputs)
    # With one supplied state, the default checks that state only; additional inputs must be supplied.
    bank=json.loads(a.tests)if a.tests else[values]
    task={'id':'interactive','task':a.question,'angle':a.angle,'constants':constants(a.question),
      'public_tests':[{'segments':[{'inputs':v}]}for v in bank],'max_commands':128,'max_frames':1024}
    if a.native:engine=Native(folder);generate=engine.generate
    else:
        import torch
        from transformers import AutoModelForCausalLM,AutoTokenizer
        from lowbit import load
        from ha_common import compact_head
        from ha_verify import generate as cpu_generate
        torch.set_num_threads(4);tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        load(model,folder/'model.mkqb');model.eval();compact_head(model,json.loads((folder/'output-token-ids.json').read_text()))
        generate=lambda text:cpu_generate(model,tokenizer,text)['reply']
    session=Session(task,arm)
    for _ in range(a.turns):
        reply=generate(session.request());session.apply(reply)
        if session.finished:break
    result={'question':a.question,'angle':a.angle,'arm':arm,'native_model_inference':a.native,
      'model_declared_done':session.finished,'loop_stopped':session.finished,'verified_task_success':None,
      'independent_verification_available':False,
      'history':session.history,'expected_answer_available':False,'public_input_states':len(bank),'only_supplied_inputs_checked':True,'harness_generation':'harness-debug-v3'}
    if session.body:
        try:
            code=assemble(session.body,session.pool,arm);actual=FullVM().execute(code,values,angle=a.angle)[0]
            result.update(program=code,requested_state_result=actual['raw']['X'],status=actual['status'])
        except (ValueError,RuntimeError,ArithmeticError)as error:result['error']=str(error)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
