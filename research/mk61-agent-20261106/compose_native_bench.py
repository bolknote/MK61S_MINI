"""Snapshot the existing native kernel and benchmark both actual Q4 exports on host."""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();repo=Path(__file__).resolve().parents[2];out=root/'native-benchmark';source=out/'source';source.mkdir(parents=True,exist_ok=True)
    reference=repo/'.build/mk61-agent-20261106/composition-v1/native-preflight/native-benchmark/source'
    frozen=reference.exists()and(reference/'mk61_ai_model.cpp').exists()
    requested=[]if frozen else['mk61_ai_model.cpp','mk61_ai_tokenizer.cpp','mk61_ai_kernels.c'];copied={}
    if frozen:
        for path in reference.iterdir():
            if path.is_file():
                data=path.read_bytes();(source/path.name).write_bytes(data);copied[path.name]=hashlib.sha256(data).hexdigest()
    while requested:
        name=requested.pop()
        if name in copied:continue
        path=repo/'code'/name;data=path.read_bytes();(source/name).write_bytes(data);copied[name]=hashlib.sha256(data).hexdigest()
        import re
        requested += [x for x in re.findall(r'#include\s+"([^"]+)"',data.decode())if x not in copied]
    for path in ([]if frozen else[repo/'tests/mk61_ai_model_probe.cpp',repo/'tools/apps/mk61ai/export_model.py']):
        data=path.read_bytes();(source/path.name).write_bytes(data);copied[path.name]=hashlib.sha256(data).hexdigest()
    subprocess.run(['clang','-std=c11','-O2','-ffp-contract=off','-fPIC','-c',str(source/'mk61_ai_kernels.c'),'-o',str(out/'kernels.o')],check=True)
    library=out/('model-probe.dylib'if platform.system()=='Darwin'else'model-probe.so')
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I',str(source),
      str(source/'mk61_ai_model.cpp'),str(source/'mk61_ai_tokenizer.cpp'),str(source/'mk61_ai_model_probe.cpp'),str(out/'kernels.o'),'-o',str(library)],check=True)
    spec=importlib.util.spec_from_file_location('compose_native_export_snapshot',source/'export_model.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    lib=C.CDLL(str(library));lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint]
    lib.mk_ai_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float),C.c_int]
    lib.mk_ai_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint),C.c_int]
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer
    torch.set_num_threads(2);sys.path.insert(0,str(repo/'research/mk61-agent-20261106'))
    from lowbit import load
    results={}
    for arm in ['champion','small']:
        folder=root/'export'/arm;weights=folder/'model.mkqb';package=out/(arm+'.mka')
        exporter.export(weights,folder/'hf/tokenizer.json',package,'lut')
        raw=package.read_bytes();buffer=C.create_string_buffer(raw)
        assert lib.mk_ai_open(buffer,len(raw))==0,'Native package load failed'
        tokenizer=AutoTokenizer.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False)
        text='МК-61. Из произведения R0 и R1 вычти R2. Ответ: '
        encoded=(C.c_ushort*2048)();used=C.c_uint()
        assert lib.mk_ai_encode(text.encode(),encoded,2048,C.byref(used),0)==0
        ids=list(encoded[:used.value]);assert ids==tokenizer.encode(text,add_special_tokens=False)
        model=AutoModelForCausalLM.from_pretrained(folder/'hf',local_files_only=True,trust_remote_code=False,attn_implementation='eager').eval();load(model,weights)
        with torch.inference_mode():reference=model(torch.tensor([ids]),use_cache=False).logits[0].numpy()
        best=C.c_ushort();logits=(C.c_float*model.config.vocab_size)();deltas=[];matches=0
        import numpy as np
        lib.mk_ai_reset()
        for i,token in enumerate(ids):
            assert lib.mk_ai_forward(token,1,C.byref(best),logits,3)==0
            got=np.ctypeslib.as_array(logits);deltas.append(float(np.abs(got-reference[i]).max()));matches+=best.value==int(reference[i].argmax())
        assert max(deltas)<.005 and matches==len(ids),(arm,max(deltas),matches,len(ids))
        # Same512 prompt tokens and exactly32 decode calls, ignoring EOS for timing.
        fixed=(ids*((512+len(ids)-1)//len(ids)))[:512];runs=[]
        for repeat in range(4):
            lib.mk_ai_reset();started=time.perf_counter()
            for i,token in enumerate(fixed):assert lib.mk_ai_forward(token,int(i==len(fixed)-1),C.byref(best),None,3)==0
            middle=time.perf_counter()
            for _ in range(32):assert lib.mk_ai_forward(best.value,1,C.byref(best),None,3)==0
            ended=time.perf_counter()
            if repeat:runs.append({'prefill_seconds':middle-started,'decode_seconds':ended-middle})
        results[arm]={'source_packet_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),'native_package_bytes':len(raw),
          'workspace_bytes':lib.mk_ai_workspace(),'cache_bytes':lib.mk_ai_cache(),'context':model.config.max_position_embeddings,
          'native_cache_storage':'FP32','arithmetic':'Native Q4 LUT with FP32 activations',
          'tokenizer_exact_for_common_prompt':True,'logit_argmax_matches':matches,'logit_positions':len(ids),'max_logit_delta':max(deltas),
          'prefill_tokens':512,'decode_calls':32,'prefill_seconds_median':statistics.median(r['prefill_seconds']for r in runs),
          'decode_tokens_per_second_median':statistics.median(32/r['decode_seconds']for r in runs),'runs':runs}
        print(json.dumps({arm:results[arm]}),flush=True)
    result={'models':results,'small_decode_speed_ratio':results['small']['decode_tokens_per_second_median']/results['champion']['decode_tokens_per_second_median'],
      'source_files_sha256':copied,'host':platform.platform(),'target_picocalc_device_measured':False,
      'same_frozen_native_kernel_as_architecture_preflight':frozen,
      'scope':'Same native Q4 kernel on the host; these timings do not measure RP2350 or PSRAM/SD bandwidth.'}
    (root/'native-host-benchmark.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
