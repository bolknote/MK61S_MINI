"""Export H32-compatible research MKA packages and verify the native boundary."""
import argparse
import ctypes as C
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import shutil
import subprocess
import time

from codec_common import ARMS,MODES,OLD_VOCAB,Protocol,TAGS,read
from course_common import program_prompt


def prepare_source(root,out,book):
    repo=Path(__file__).resolve().parents[2]
    reference=repo/'.build/mk61-agent-20261106/composition-v1/server-results/native-benchmark/source'
    src=out/'source';src.mkdir(parents=True,exist_ok=True)
    for f in reference.iterdir():
        if f.is_file():shutil.copyfile(f,src/f.name)
    shutil.copyfile(Path(__file__).with_name('codec_native_bridge.hpp'),src/'codec_native_bridge.hpp')
    path=src/'mk61_ai_model.cpp';text=path.read_text();needle='''      if (!row(t, r))
        return false;
      float value = 0;''';assert text.count(needle)==1
    path.write_text(text.replace(needle,'''      if (head && allowed && !allowed(policy, std::uint16_t(r))) {
        if (logits) logits[r] = -FLT_MAX;
        continue;
      }
'''+needle))
    words=[];lengths=[]
    for byte in range(256):
        sequence=book['byte_to_symbols'][f'{byte:02X}'];word=0
        for symbol in sequence:word=word*32+symbol
        words.append(word);lengths.append(len(sequence))
    assert max(lengths)<=6
    (src/'codec_table.hpp').write_text('#include <cstdint>\nstatic const std::uint32_t codec_words[256]={'+','.join(map(str,words))+'};\nstatic const std::uint8_t codec_lengths[256]={'+','.join(map(str,lengths))+'};\n')
    probe=src/'mk61_ai_model_probe.cpp';probe.write_text(probe.read_text()+'''
#include "codec_native_bridge.hpp"
#include "codec_table.hpp"
namespace { std::vector<unsigned char> codec_mask; }
extern "C" void codec_set_mask(const unsigned short *ids, unsigned n) {
  codec_mask.assign(model.config().vocab, 0);
  for (unsigned i=0;i<n;++i) if (ids[i]<codec_mask.size()) codec_mask[ids[i]]=1;
}
extern "C" int codec_forward(unsigned short token, int output,
  unsigned short *best, float *logits) {
  return int(model.forward(token, output, *best, service, nullptr,
    mk61ai::Arithmetic::LUT_FLOAT32, logits,
    [](void *,std::uint16_t id){return codec_mask[id]!=0;},nullptr));
}
extern "C" int codec_encode(const char *text, unsigned short *out,
  unsigned capacity, unsigned *used) {
  return int(mk61research::encode_h32(model,text,out,capacity,*used));
}
extern "C" int codec_decode_body(const char *text,unsigned char *out,
  unsigned capacity,unsigned *used) {
  return mk61research::Huffman32{codec_words,codec_lengths,CODEC_MAX}.decode(text,out,capacity,*used)?1:0;
}
'''.replace('CODEC_MAX',str(max(lengths))))
    subprocess.run(['clang','-std=c11','-O2','-ffp-contract=off','-fPIC','-c',str(src/'mk61_ai_kernels.c'),'-o',str(out/'kernels.o')],check=True)
    library=out/'codec-probe.dylib'
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I',str(src),str(src/'mk61_ai_model.cpp'),
      str(src/'mk61_ai_tokenizer.cpp'),str(probe),str(out/'kernels.o'),'-o',str(library)],check=True)
    spec=importlib.util.spec_from_file_location('codec_native_export',src/'export_model.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    return src,library,exporter


def native_tokenizer(hf,destination):
    data=json.loads((hf/'tokenizer.json').read_text());added=[x for x in data['added_tokens']if x['id']>=OLD_VOCAB]
    assert [(x['id'],x['content'])for x in added]==[(OLD_VOCAB+i,t)for i,t in enumerate(TAGS)]
    for token in added:
        assert not any(token.get(k)for k in ['special','normalized','lstrip','rstrip','single_word'])
        data['model']['vocab'][token['content']]=token['id']
    data['added_tokens']=[x for x in data['added_tokens']if x['id']<3]
    assert len(data['model']['vocab'])==OLD_VOCAB+32
    destination.write_text(json.dumps(data,ensure_ascii=False)+'\n')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--preflight',action='store_true');a=ap.parse_args();root=a.root.resolve()
    book=json.loads((root/'codebook-32.json').read_text());out=root/('native-preflight'if a.preflight else'native');out.mkdir(exist_ok=True)
    src,library,exporter=prepare_source(root,out,book);lib=C.CDLL(str(library))
    lib.mk_ai_open.argtypes=[C.c_void_p,C.c_uint];lib.codec_set_mask.argtypes=[C.POINTER(C.c_ushort),C.c_uint]
    lib.codec_forward.argtypes=[C.c_ushort,C.c_int,C.POINTER(C.c_ushort),C.POINTER(C.c_float)]
    lib.codec_encode.argtypes=[C.c_char_p,C.POINTER(C.c_ushort),C.c_uint,C.POINTER(C.c_uint)]
    lib.codec_decode_body.argtypes=[C.c_char_p,C.POINTER(C.c_ubyte),C.c_uint,C.POINTER(C.c_uint)]
    lib.mk_ai_decode.argtypes=[C.c_ushort,C.c_char_p,C.c_uint,C.POINTER(C.c_uint)]
    p32=Protocol('h32',book);buffer_out=(C.c_ubyte*105)();used=C.c_uint();checks=0
    rng=random.Random(6114520)
    for code in [[i]for i in range(256)]+[[rng.randrange(256)for _ in range(rng.randrange(1,106))]for _ in range(100)]:
        body=p32.body(code);assert lib.codec_decode_body(body.encode(),buffer_out,105,C.byref(used))==1
        assert list(buffer_out[:used.value])==code;checks+=1
    word=next(x for x in p32.codec.codebook.values()if len(x)>1)
    invalid=['','garbage','<h32>',''.join(TAGS[i]for i in word[:-1]),p32.body([0]*106)]
    for text in invalid:assert lib.codec_decode_body(text.encode(),buffer_out,105,C.byref(used))==0
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    from codec_common import compact_head
    from lowbit import load
    torch.set_num_threads(4);results={}
    for arm in ARMS:
        for mode in MODES:
            name=arm+'-'+mode;p=Protocol(mode,book)
            folder=root/'initial-cache'/arm if a.preflight else root/'export/endpoint'/name
            weights=folder/('initial.mkqb'if a.preflight else'model.mkqb');hf=folder/'hf'
            config=json.loads((hf/'config.json').read_text());ids_allowed=json.loads((root/f'output-{mode}.json').read_text())
            tokenizer=AutoTokenizer.from_pretrained(hf,local_files_only=True,trust_remote_code=False)
            adapted=out/(name+'-native-tokenizer.json');native_tokenizer(hf,adapted)
            package=out/(name+'.mka');exporter.export(weights,adapted,package,'lut');data=package.read_bytes();package_buffer=C.create_string_buffer(data)
            assert lib.mk_ai_open(package_buffer,len(data))==0
            allowed=(C.c_ushort*len(ids_allowed))(*ids_allowed);lib.codec_set_mask(allowed,len(ids_allowed))
            model=AutoModelForCausalLM.from_pretrained(hf,local_files_only=True,trust_remote_code=False,attn_implementation='eager').eval();load(model,weights);compact_head(model,ids_allowed)
            known=read(root/'train.jsonl')[:3];texts=[]
            for task in known:
                texts.append(program_prompt(task));texts.append(program_prompt({**task,'initial_code':task['reference_code']},observation='TRACE 02:10 X=60; ожидалось X=10'))
            encoded=(C.c_ushort*2048)();count=C.c_uint();tokenizer_checks=0
            for text in texts:
                native_text=p.encode_text(text);expected=tokenizer.encode(native_text,add_special_tokens=False)
                assert lib.codec_encode(native_text.encode(),encoded,2048,C.byref(count))==0
                assert list(encoded[:count.value])==expected;tokenizer_checks+=1
            chars=C.create_string_buffer(32);nchars=C.c_uint()
            for i,tag in enumerate(TAGS):
                assert lib.mk_ai_decode(OLD_VOCAB+i,chars,32,C.byref(nchars))==0
                assert chars.raw[:nchars.value].decode()==tag
            common=tokenizer.encode('МК-61. Найди разность показаний R0 и R1. Ответ: ',add_special_tokens=False)
            with torch.inference_mode():reference=model(torch.tensor([common]),use_cache=False).logits[0]
            best=C.c_ushort();logits=(C.c_float*config['vocab_size'])();errors=[];matches=0;lib.mk_ai_reset()
            for i,token in enumerate(common):
                assert lib.codec_forward(token,1,C.byref(best),logits)==0
                errors.append(max(abs(logits[j]-float(reference[i,j]))for j in ids_allowed));matches+=best.value==int(reference[i].argmax())
            assert max(errors)<.005 and matches==len(common),(name,max(errors),matches,len(common))
            results[name]={'source_packet_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),'native_package_bytes':len(data),
              'input_tokenizer_probes_matched':tokenizer_checks,'added_token_decodes_matched':32,'logit_positions':len(common),
              'logit_argmax_matches':matches,'max_logit_difference':max(errors),'compact_output_rows':len(ids_allowed),
              'workspace_bytes':lib.mk_ai_workspace(),'cache_bytes':lib.mk_ai_cache(),'native_cache_storage':'FP32'}
            if a.preflight:
                cases=[{'id':t['id'],'prompt':program_prompt(t)}for t in known[:2]]
            else:
                fresh=json.loads((root/f'results/{name}-endpoint.json').read_text())
                cases=[row for part in ['manual1','manual2','manual3']for row in fresh['metrics'][part]['program']['details'][:2]]
            generations=[]
            for row in cases:
                text=p.encode_text(row['prompt']);inputs=tokenizer.encode(text,add_special_tokens=False)
                assert lib.codec_encode(text.encode(),encoded,2048,C.byref(count))==0
                assert list(encoded[:count.value])==inputs
                lib.mk_ai_reset();started=time.perf_counter()
                for i,token in enumerate(inputs):assert lib.codec_forward(token,int(i==len(inputs)-1),C.byref(best),None)==0
                middle=time.perf_counter();tokens=[]
                for _ in range(160):
                    token=best.value
                    if token==tokenizer.eos_token_id:break
                    tokens.append(token);assert lib.codec_forward(token,1,C.byref(best),None)==0
                ended=time.perf_counter()
                if a.preflight:
                    with torch.inference_mode():output=model.generate(input_ids=torch.tensor([inputs]),attention_mask=torch.ones((1,len(inputs)),dtype=torch.long),
                      max_new_tokens=160,do_sample=False,use_cache=True,pad_token_id=tokenizer.pad_token_id or 0,eos_token_id=tokenizer.eos_token_id)
                    expected=output[0,len(inputs):].tolist()
                    if tokenizer.eos_token_id in expected:expected=expected[:expected.index(tokenizer.eos_token_id)]
                else:expected=row['generated_token_ids']
                pieces=[];piece=C.create_string_buffer(256)
                for token in tokens:
                    assert lib.mk_ai_decode(token,piece,256,C.byref(nchars))==0;pieces.append(piece.raw[:nchars.value])
                native_text=b''.join(pieces).decode('utf8')
                assert native_text==tokenizer.decode(tokens,skip_special_tokens=True,clean_up_tokenization_spaces=False)
                import re
                match=re.search(r'<write>(.*?)</write>',native_text,re.S)
                if mode=='h32'and match:
                    ok=lib.codec_decode_body(match.group(1).encode(),buffer_out,105,C.byref(used))
                    try:decoded=p.bytes(match.group(1))
                    except ValueError:decoded=None
                    assert bool(ok)==(decoded is not None)
                    if ok:assert list(buffer_out[:used.value])==decoded
                generations.append({'id':row['id'],'token_ids_match_reference':tokens==expected,'native_reply':native_text,
                  'native_tokens':len(tokens),'prefill_seconds':middle-started,'decode_seconds':ended-middle})
            results[name].update(greedy_generations_matched=sum(x['token_ids_match_reference']for x in generations),
              greedy_generations_total=len(generations),generation_details=generations)
            # Controlled per-token timing; identical input stream for every
            # format, independently of model answer length or correctness.
            fixed=(common*((512+len(common)-1)//len(common)))[:512]
            stream=tokenizer.encode('<calc>+ R0 R1</calc><write>60 61 10 50</write><run/>',add_special_tokens=False)[:32]
            runs=[]
            for repeat in range(4):
                lib.mk_ai_reset();start=time.perf_counter()
                for i,token in enumerate(fixed):assert lib.codec_forward(token,int(i==len(fixed)-1),C.byref(best),None)==0
                middle=time.perf_counter()
                for token in stream:assert lib.codec_forward(token,1,C.byref(best),None)==0
                end=time.perf_counter()
                if repeat:runs.append({'prefill_seconds':middle-start,'decode_seconds':end-middle})
            import statistics
            results[name].update(prefill512_seconds_median=statistics.median(x['prefill_seconds']for x in runs),
              decode_tokens_per_second_median=statistics.median(len(stream)/x['decode_seconds']for x in runs),timing_runs=runs)
            print(json.dumps({name:{k:v for k,v in results[name].items()if k not in ['generation_details','timing_runs']}},ensure_ascii=False),flush=True)
            del model
    report={'models':results,'portable_decoder_valid_roundtrips':checks,'portable_decoder_invalid_inputs_rejected':len(invalid),
      'preflight':a.preflight,'source_files_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest()for f in src.iterdir()if f.is_file()},
      'research_bridge_and_original_russian_bpe':True,'product_runtime_sources_modified':False,'native_picocalc_measured':False,
      'native_cache_storage':'FP32','scope':'Frozen native host kernel with new-token bridge and compact row projection; physical PicoCalc not tested.'}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()
