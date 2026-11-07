"""Private frozen-runtime experiment: keep Russian input, project selected output rows.

This changes a research snapshot, never the shared product/runtime sources.
The selected rows cover the current bounded arithmetic/tool serialization;
they are not asserted to cover free-form Russian generation.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import time


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    source=root/'native-benchmark/source';out=root/'codec-study/native-head';private=out/'source';private.mkdir(parents=True,exist_ok=True)
    for f in source.iterdir():
        if f.is_file():shutil.copyfile(f,private/f.name)
    path=private/'mk61_ai_model.cpp';text=path.read_text();needle='''      if (!row(t, r))
        return false;
      float value = 0;'''
    assert text.count(needle)==1
    replacement='''      // Research-only selective output projection. All input rows remain.
      if (head && allowed && !allowed(policy, std::uint16_t(r))) {
        if (logits)
          logits[r] = -FLT_MAX;
        continue;
      }
'''+needle
    path.write_text(text.replace(needle,replacement))
    probe=private/'mk61_ai_model_probe.cpp'
    probe.write_text(probe.read_text()+'''
namespace { std::vector<unsigned char> output_mask; }
extern "C" void mk_ai_set_output_mask(const unsigned short *ids, unsigned n) {
  output_mask.assign(model.config().vocab, 0);
  for (unsigned i = 0; i < n; ++i)
    if (ids[i] < output_mask.size()) output_mask[ids[i]] = 1;
}
extern "C" int mk_ai_forward_masked(unsigned short token, int output,
  unsigned short *best, float *logits, int arithmetic) {
  return int(model.forward(token, output, *best, service, nullptr,
    static_cast<mk61ai::Arithmetic>(arithmetic), logits,
    [](void *, std::uint16_t id) { return output_mask[id] != 0; }, nullptr));
}
''')
    subprocess.run(['clang','-std=c11','-O2','-ffp-contract=off','-fPIC','-c',str(private/'mk61_ai_kernels.c'),'-o',str(out/'kernels.o')],check=True)
    library=out/'probe.dylib'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I',str(private),
      str(private/'mk61_ai_model.cpp'),str(private/'mk61_ai_tokenizer.cpp'),str(probe),str(out/'kernels.o'),'-o',str(library)],check=True)
    lib=C.CDLL(str(library));lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint]
    args=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float),C.c_int]
    lib.mk_ai_forward.argtypes=args;lib.mk_ai_forward_masked.argtypes=args
    lib.mk_ai_set_output_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    ids=json.loads((root/'codec-study/output-token-ids.json').read_text());allowed=(C.c_ushort*len(ids))(*ids)
    from transformers import AutoTokenizer
    from course_common import program_prompt
    selected=[]
    for level in [2,3]:
        tasks=[json.loads(x)for x in(root/f'development{level}.jsonl').read_text().splitlines()]
        selected += [tasks[i]for i in [0,8,20]]
    results={}
    for arm in ['champion','small']:
        package=root/'native-benchmark'/(arm+'.mka');data=package.read_bytes();buffer=C.create_string_buffer(data)
        assert lib.mk_ai_open(buffer,len(data))==0
        lib.mk_ai_set_output_mask(allowed,len(ids))
        tokenizer=AutoTokenizer.from_pretrained(root/'export'/arm/'hf',local_files_only=True,trust_remote_code=False)
        best=C.c_ushort();vocab=len(tokenizer);logits=(C.c_float*vocab)()
        common=tokenizer.encode('МК-61. Из произведения R0 и R1 вычти R2. Ответ: ',add_special_tokens=False)
        full=[];lib.mk_ai_reset()
        for token in common:
            assert lib.mk_ai_forward(token,1,C.byref(best),logits,3)==0
            full.append([logits[i]for i in ids])
        errors=[];argmax=0;lib.mk_ai_reset()
        for at,token in enumerate(common):
            assert lib.mk_ai_forward_masked(token,1,C.byref(best),logits,3)==0
            values=[logits[i]for i in ids];errors.append(max(abs(a-b)for a,b in zip(values,full[at])))
            argmax+=best.value==ids[max(range(len(ids)),key=lambda j:full[at][j])]
        assert max(errors)==0 and argmax==len(common)
        prompt=(common*((512+len(common)-1)//len(common)))[:512]
        stream=tokenizer.encode('<calc>+ R0 R1</calc><write>60 61 10 50</write><run/>',add_special_tokens=False)[:32]
        assert len(stream)==32;measurements={}
        for name,forward in [('full8192',lib.mk_ai_forward),('selected',lib.mk_ai_forward_masked)]:
            runs=[]
            for repeat in range(4):
                lib.mk_ai_reset();start=time.perf_counter()
                for i,token in enumerate(prompt):assert forward(token,int(i==len(prompt)-1),C.byref(best),None,3)==0
                middle=time.perf_counter()
                for token in stream:assert forward(token,1,C.byref(best),None,3)==0
                end=time.perf_counter()
                if repeat:runs.append({'prefill_seconds':middle-start,'decode_seconds':end-middle})
            measurements[name]={'prefill_seconds_median':statistics.median(x['prefill_seconds']for x in runs),
              'decode_tokens_per_second_median':statistics.median(32/x['decode_seconds']for x in runs),'runs':runs}
        generations=[]
        def generate(task,forward):
            prompt=tokenizer.encode(program_prompt(task),add_special_tokens=False);lib.mk_ai_reset()
            for at,token in enumerate(prompt):assert forward(token,int(at==len(prompt)-1),C.byref(best),None,3)==0
            tokens=[]
            for _ in range(128):
                token=best.value
                if token==tokenizer.eos_token_id:break
                tokens.append(token)
                assert forward(token,1,C.byref(best),None,3)==0
            return tokens
        for task in selected:
            full_tokens=generate(task,lib.mk_ai_forward);small_tokens=generate(task,lib.mk_ai_forward_masked)
            generations.append({'id':task['id'],'identical_token_ids':full_tokens==small_tokens,
              'full_output_token_ids_all_allowed':set(full_tokens)<=set(ids),
              'full_reply':tokenizer.decode(full_tokens,skip_special_tokens=True),
              'selected_reply':tokenizer.decode(small_tokens,skip_special_tokens=True)})
        results[arm]={'source_package_sha256':hashlib.sha256(data).hexdigest(),'measurements':measurements,
          'decode_speed_ratio':measurements['selected']['decode_tokens_per_second_median']/measurements['full8192']['decode_tokens_per_second_median'],
          'allowed_logits_max_difference':max(errors),'argmax_among_allowed_matches':argmax,'logit_positions':len(common),
          'identical_greedy_generations':sum(x['identical_token_ids']for x in generations),'generation_probes':len(generations),'details':generations,
          'model_parameters_unchanged':True,'input_vocabulary':vocab,'output_rows_computed':len(ids)}
        print(json.dumps({arm:{k:v for k,v in results[arm].items()if k!='details'}},ensure_ascii=False),flush=True)
    report={'models':results,'models_or_product_sources_modified':False,'private_research_source_modified':True,
      'source_files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()for f in private.iterdir()if f.is_file()},
      'training_performed':False,'weights_memory_saved':0,'native_picocalc_measured':False,
      'scope':'Same native host Q4 kernel; fixed identical512-token prefill and32-token decode stream. Output-row skipping only; no new opcode codec or training.'}
    (root/'codec-study/head-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
