"""Reproduce the user's sine request with actual Q4 replies and the real core."""
import ctypes as C
import json
import math
from pathlib import Path
import subprocess

import torch
from transformers import AutoModelForCausalLM,AutoTokenizer

from semantic_common import ROOT,sha,write_json,compact_head,protocol
from codec_eval import generate_batch
from course_common import program_prompt
from emulator import Emulator
from harness import extract_code,close_number
from lowbit import load


def main():
    root=ROOT/'server-results';out=root/'sine-probe';out.mkdir(exist_ok=True)
    here=Path(__file__).parent;repo=here.parents[1]
    # Private degree-mode copy of the research bridge; product/core sources
    # remain unchanged. Both references must match the known mathematical sine.
    source=(here/'core_bridge.cpp').read_text();assert source.count('MK61Emu_SetAngleUnit(RADIAN);')==1
    degree_source=out/'core_bridge_degrees.cpp';degree_source.write_text(source.replace('MK61Emu_SetAngleUnit(RADIAN);','MK61Emu_SetAngleUnit(DEGREE);'))
    degree_library=out/'libmk61-degrees.so'
    subprocess.run(['c++','-std=c++17','-O2','-fPIC','-shared','-DMK61_CORE_STANDALONE=1','-DMK61_CORE_HOT_TABLES_IN_SRAM=0',
      '-I',str(repo/'code'),str(degree_source),str(repo/'code/mk61emu_core.cpp'),'-o',str(degree_library)],check=True,capture_output=True)
    engines={'radians':Emulator(),'degrees':Emulator(degree_library)}
    references={mode:em.run([0x60,0x1C,0x50],{'R0':22})for mode,em in engines.items()}
    expected={'radians':math.sin(22),'degrees':math.sin(math.radians(22))}
    assert all(close_number(references[m]['X'],expected[m])for m in engines),references
    torch.set_num_threads(4);folder=root/'export/selected-budget'
    tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
    allowed=json.loads((folder/'output-token-ids.json').read_text())
    texts=['Подсчитай синус 22.','Подсчитай синус 22 градусов.','Подсчитай синус 22 радиан.',
      'В R0 записан угол в радианах. Вычисли синус R0, результат оставь в X.',
      'Возведи R0 в квадрат, результат оставь в X.','Найди сумму R0 и R1.']
    prompts=[program_prompt({'task':text,'public_tests':[],'hidden_tests':[]})for text in texts]
    results={};selected_replies=None
    for label in ['selected-budget','direct-endpoint','auxiliary-endpoint']:
        source=root/'export'/label
        model=AutoModelForCausalLM.from_pretrained(source/'hf',local_files_only=True,trust_remote_code=False);load(model,source/'model.mkqb');model.eval()
        original_head=model.lm_head.forward;compact_head(model,allowed)
        replies=generate_batch(model,tokenizer,prompts,protocol('hex'),max_new=128)
        rows=[]
        for text,prompt,reply in zip(texts,prompts,replies):
            code=extract_code(reply['reply'])
            executed={mode:{'zero_registers':em.run(code,{}),'R0_22_R1_2':em.run(code,{'R0':22,'R1':2})}for mode,em in engines.items()}if code else{}
            rows.append({'text':text,'prompt':prompt,'code':code,'execution':executed,**reply})
        results[label]={'packet_sha256':sha(source/'model.mkqb'),'compact_head':True,'rows':rows}
        print(json.dumps({'model':label,'answers':[{'text':r['text'],'reply':r['raw_reply'],'X_R0_22':r['execution'].get('radians',{}).get('R0_22_R1_2',{}).get('X')}for r in rows]},ensure_ascii=False),flush=True)
        if label=='selected-budget':
            selected_replies=replies
            model.lm_head.forward=original_head
            free=generate_batch(model,tokenizer,prompts[:1],protocol('hex'),max_new=96)[0]
            results['selected_without_output_mask']={'text':texts[0],**free}
            print(json.dumps({'without_output_mask':free['raw_reply']},ensure_ascii=False),flush=True)
        del model
    # Same request through the frozen C++ kernel and the actual 1024 MKA.
    lib=C.CDLL(str(root/'native/codec-probe.dylib'))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    data=(folder/'model-context1024.mka').read_bytes();buffer=C.create_string_buffer(data);assert lib.mk_ai_open(buffer,len(data))==0
    mask=(C.c_ushort*len(allowed))(*allowed);lib.codec_set_mask(mask,len(allowed));native=[]
    for prompt,reference in zip(prompts,selected_replies):
        ids=tokenizer.encode(prompt,add_special_tokens=False);lib.mk_ai_reset();best=C.c_ushort()
        for i,token in enumerate(ids):assert lib.codec_forward(token,int(i+1==len(ids)),C.byref(best),None)==0
        generated=[]
        for _ in range(128):
            token=best.value
            if token==tokenizer.eos_token_id:break
            generated.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
        native.append({'matches_cpu':generated==reference['generated_token_ids'],'reply':tokenizer.decode(generated,skip_special_tokens=True,clean_up_tokenization_spaces=False)})
    assert all(x['matches_cpu']for x in native)
    result={'requests':texts,'results':results,'native_selected':native,'native_matches':sum(x['matches_cpu']for x in native),
      'pipe_available_in_compact_output':any('|'in tokenizer.decode([x])for x in allowed),
      'sine_in_current_natural_language_training_grammar':False,'reference_expected':expected,'real_core_reference':references,
      'reference_opcode_source':'/Users/bolk/Projects/MK-61/tests/emulator/mk61.cjs:104',
      'preloading_R0_22_is_explicit_diagnostic_not_an_automatic_literal_parser':True,
      'device_UI_not_executed':True,'product_files_changed':False}
    write_json(out/'results.json',result);print(json.dumps({'native_matches':result['native_matches'],'path':str(out/'results.json')}),flush=True)


if __name__=='__main__':main()
