"""Private native FP16 KV storage prototype and post-exam verification.

The model keeps FP32 arithmetic. Only cache I/O converts to IEEE binary16.
Product sources and immutable parent packages are never edited.
"""
import argparse
import ctypes as C
import json
from pathlib import Path
import statistics
import struct
import subprocess
import time
import torch
from bt_common import ROOT,SOURCE,CONFIGS,read,write,sha,check_frozen,output_ids,compact_head,ACTIONS,ACTION_IDS,CORRECT_IDS
from codec_common import ROOT as CODEC_ROOT
from codec_native import native_tokenizer
from ap_native import prepare_source as original_prepare
from ac_verify import verify_parser
from ac_native import OLD_ACTIONS
from aq_protocol import prompt_ids,header_ids
from bt_decode import generate
from native_export import packet
from native_verify import verify_export
import ay_native as base


def prepare(root):
    out=root/'native';out.mkdir(parents=True,exist_ok=True)
    src,library,exporter=original_prepare(root,out,read(CODEC_ROOT/'codebook-32.json'))
    p=src/'mk61_ai_model_probe.cpp';s=p.read_text()
    s=s.replace('std::vector<std::uint8_t> cache;','std::vector<std::uint8_t> cache;\nbool half_cache = false;\nunsigned logical_cache_bytes = 0;')
    a=s.index('bool read_cache(');b=s.index('bool service(',a)
    s=s[:a]+'''bool read_cache(void *, std::uint32_t at, void *p, unsigned n) {
  if (at > logical_cache_bytes || n > logical_cache_bytes - at) return false;
  if (!half_cache) { std::memcpy(p, cache.data() + at, n); return true; }
  if ((at | n) & 3) return false;
  for (unsigned i=0; i<n; i+=4) {
    _Float16 h; std::memcpy(&h, cache.data()+(at+i)/2, 2);
    float f = float(h); std::memcpy(static_cast<unsigned char *>(p)+i, &f, 4);
  }
  return true;
}
bool write_cache(void *, std::uint32_t at, const void *p, unsigned n) {
  if (at > logical_cache_bytes || n > logical_cache_bytes - at) return false;
  if (!half_cache) { std::memcpy(cache.data()+at, p, n); return true; }
  if ((at | n) & 3) return false;
  for (unsigned i=0; i<n; i+=4) {
    float f; std::memcpy(&f, static_cast<const unsigned char *>(p)+i, 4);
    _Float16 h = _Float16(f); std::memcpy(cache.data()+(at+i)/2, &h, 2);
  }
  return true;
}
''' +s[b:]
    assert s.count('cache.resize(model.cache_bytes());')==1
    s=s.replace('cache.resize(model.cache_bytes());','logical_cache_bytes = model.cache_bytes();\n  std::vector<std::uint8_t>(logical_cache_bytes/(half_cache ? 2 : 1)).swap(cache);')
    s=s.replace('{nullptr, unsigned(cache.size()), read_cache, write_cache}','{nullptr, logical_cache_bytes, read_cache, write_cache}')
    s+='''
extern "C" void codec_half_storage(int enabled) { half_cache = enabled != 0; }
extern "C" unsigned codec_physical_cache_bytes() { return unsigned(cache.capacity()); }
extern "C" unsigned short codec_half_bits(float value) {
  _Float16 h = _Float16(value); unsigned short bits; std::memcpy(&bits,&h,2); return bits;
}
'''
    p.write_text(s)
    # Private tokenizer workspace permits full Russian input at context 1536.
    p=src/'mk61_ai_model.hpp';s=p.read_text();assert 'MAX_TEXT = 8192'in s;p.write_text(s.replace('MAX_TEXT = 8192','MAX_TEXT = 16384'))
    subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I',str(src),
       str(src/'mk61_ai_model.cpp'),str(src/'mk61_ai_tokenizer.cpp'),str(src/'mk61_ai_model_probe.cpp'),str(out/'kernels.o'),'-o',str(library)],check=True)
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True)
    native_tokenizer(SOURCE/'hf',out/'tokenizer.json');h,payload=packet(SOURCE/'model.mkqb')
    sizes={}
    for name,config in CONFIGS.items():
        folder=root/'export'/name;folder.mkdir(parents=True,exist_ok=True);h['config']['max_position_embeddings']=config['context']
        raw=json.dumps(h,ensure_ascii=False,separators=(',',':')).encode();derived=out/(name+'.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        exporter.export(derived,out/'tokenizer.json',folder/'model.mka','lut')
        write(folder/'output-token-ids.json',output_ids(tok));write(folder/'protocol.json',{'neural_headers':{x:header_ids(tok,x)for x in ['write','run','diag']}})
        sizes[name]={'mka_bytes':(folder/'model.mka').stat().st_size,'sha256':sha(folder/'model.mka'),'context':config['context'],'weight_payload_unchanged':True}
    parser=verify_parser(out,tok)
    base.ARMS=list(CONFIGS);engine=Engine(root)
    lib=engine.lib;lib.codec_half_bits.argtypes=[C.c_float];lib.codec_half_bits.restype=C.c_ushort
    generator=torch.Generator().manual_seed(261109113);numbers=torch.cat([torch.randn(10000,generator=generator)*100,
        torch.tensor([0.,-0.,65504.,65520.,2**-24,2**-25,1.+2**-11,1.+3*2**-11])]).float()
    expected=numbers.half().view(torch.int16).tolist()
    for value,bits in zip(numbers.tolist(),expected):assert lib.codec_half_bits(value)==bits&65535
    write(root/'native-prepared.json',{'complete':True,'packages':sizes,'half_rounding_checks':len(numbers),'parser':parser,
        'product_sources_modified':False,'physical_PicoCalc_measured':False,'source_sha256':sha(__file__),
        'private_sources':{p.name:sha(p)for p in src.iterdir()if p.is_file()}})
    return engine,tok


class Engine(base.Engine):
    def open(self,role='tool'):
        if self.role==self.tool:return
        self.context=CONFIGS[self.tool]['context'];self.lib.codec_half_storage(int(CONFIGS[self.tool]['KV']=='FP16'))
        super().open(role)
        expected=self.context*2*10*2*32*(2 if CONFIGS[self.tool]['KV']=='FP16'else 4)
        assert self.lib.codec_physical_cache_bytes()==expected

    def prefill(self,text,segmented=False):
        assert segmented and text.endswith('<')and len(text.encode())<=16384
        encoded=(C.c_ushort*self.context)();used=C.c_uint();best=C.c_ushort()
        if self.lib.codec_encode(text[:-1].encode(),encoded,self.context-1,C.byref(used))!=0:return None
        encoded[used.value]=30;used.value+=1
        if used.value>=self.context-8:return None
        inputs=list(encoded[:used.value]);allowed=ACTION_IDS+CORRECT_IDS;ids=(C.c_ushort*len(allowed))(*allowed)
        self.lib.codec_set_mask(ids,len(allowed));logits=(C.c_float*8224)();self.lib.mk_ai_reset()
        for at,token in enumerate(inputs):
            last=at+1==len(inputs);assert self.lib.codec_forward(token,int(last),C.byref(best),logits if last else None)==0
        best.value=ACTION_IDS[ACTIONS.index(self.forced_action)]if self.forced_action else max(ACTION_IDS,key=lambda i:logits[i])
        self.last_margin=float(logits[CORRECT_IDS[1]]-logits[CORRECT_IDS[0]])
        return inputs,best

    def generate(self,text,forced_action=None):
        self.forced_action=forced_action;self.open();p=self.parser;p.ab_reset();self.mask(True);state=self.prefill(text,True)
        if state is None:return {'codec_error':'context_overflow','action':None,'body':[],'generated_token_ids':[]}
        inputs,best=state;token=best.value;assert p.ab_accept(token,self.pieces[token]);tokens=[token]
        if not p.ab_complete():
            action=OLD_ACTIONS[p.ab_action()];header=self.headers[action];self.mask(True)
            for i,token in enumerate(header):assert self.lib.codec_forward(token,int(i+1==len(header)),C.byref(best),None)==0
        else:header=[]
        for _ in range(0 if p.ab_complete()else min(511,self.context-len(inputs)-len(header))):
            token=best.value;assert p.ab_accept(token,self.pieces[token])
            if token!=30:tokens.append(token)
            if p.ab_complete():break
            self.mask(True);assert self.lib.codec_forward(token,1,C.byref(best),None)==0
        if not p.ab_complete():return {'action':None,'body':[],'codec_error':'incomplete','generated_token_ids':tokens,'input_token_ids':inputs}
        body=(C.c_ubyte*512)();n=p.ab_body(body)
        return {'action':OLD_ACTIONS[p.ab_action()],'body':list(body[:n]),'codec_error':None,'generated_token_ids':tokens,'input_token_ids':inputs}


def probes(report):
    output=[];seen=set()
    def add(p,g,forced=None):
        if p in seen or g.get('codec_error'):return
        seen.add(p);output.append({'prompt':p,'generation':g,'forced':forced})
    for r in report['primary']['records'][:2]:add(r['prompt'],r['generation'],'write')
    histories=[h for mode in ['own','wrong','gold']for r in report[mode]['records']for h in r['history']if 'generation'in h]
    for action in ACTIONS:
        for h in [h for h in histories if h['generation'].get('action')==action][:2]:add(h['prompt'],h['generation'],'write'if h['kind']=='replan'else None)
    for h in sorted(histories,key=lambda h:h['generation'].get('input_tokens',0))[-3:]:add(h['prompt'],h['generation'],'write'if h['kind']=='replan'else None)
    return output


def verify(root):
    check_frozen();assert read(root/'controller-complete.json')['all_own_workers_joined'];base.ARMS=list(CONFIGS);engine=Engine(root)
    model,exact=verify_export(SOURCE)
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(SOURCE/'hf',local_files_only=True);compact_head(model,output_ids(tok));results={}
    for name in read(root/'complete.json')['closed_evaluated']:
        engine.tool=name;engine.role=None;details=[]
        for probe in probes(read(root/('closed-'+name+'.json'))):
            p=probe['prompt'];forced=probe['forced'];gpu=probe['generation'];cpu=generate(model,tok,[p],CONFIGS[name],forced)[0];native=engine.generate(p,forced)
            assert native['input_token_ids']==prompt_ids(tok,p)
            assert native['generated_token_ids']==cpu['generated_token_ids']==gpu['generated_token_ids'],(name,probe,native,cpu)
            details.append({'action':gpu['action'],'input_tokens':len(prompt_ids(tok,p)),'B200_CPU_CPP_equal':True})
        results[name]={'probes':details,'actual_physical_KV_bytes':engine.lib.codec_physical_cache_bytes(),
           'logical_FP32_cache_bytes':engine.lib.mk_ai_cache(),'workspace_bytes':engine.lib.mk_ai_workspace()}
        print({'verified':name,'probes':len(details)},flush=True)
    write(root/'native-verification.json',{'complete':True,'configs':results,'parent_export':exact,'source_sha256':sha(__file__),
        'streams_verified':sum(len(r['probes'])for r in results.values()),'physical_PicoCalc_measured':False,'selection_changed':False})


def benchmark(root):
    base.ARMS=list(CONFIGS);engine=Engine(root);results={};token=100;best=C.c_ushort()
    for name in ['baseline','half1024','context1536']:
        engine.tool=name;engine.role=None;engine.open();allowed=output_ids(None)if False else read(root/'export'/name/'output-token-ids.json')
        ids=(C.c_ushort*len(allowed))(*allowed);engine.lib.codec_set_mask(ids,len(allowed))
        # Prefill + fixed 32-token decode must fit the declared capacity.
        for length in [512,992]+([1504]if name=='context1536'else[]):
            times=[]
            for repeat in range(4):
                engine.lib.mk_ai_reset();start=time.perf_counter()
                for i in range(length):assert engine.lib.codec_forward(token,int(i==length-1),C.byref(best),None)==0
                middle=time.perf_counter()
                for i in range(32):assert engine.lib.codec_forward(token,1,C.byref(best),None)==0
                end=time.perf_counter()
                if repeat:times.append({'prefill_seconds':middle-start,'decode_seconds':end-middle})
            results[name+':'+str(length)]={'prefill_tokens':length,'decode_tokens':32,'runs':times,
               'prefill_seconds_median':statistics.median(t['prefill_seconds']for t in times),
               'decode_tokens_per_second_median':statistics.median(32/t['decode_seconds']for t in times),
               'KV_bytes':engine.lib.codec_physical_cache_bytes(),'workspace_bytes':engine.lib.mk_ai_workspace()}
            print({'benchmark':name,'context':length},flush=True)
    write(root/'native-timing.json',{'complete':True,'host_only':True,'physical_PicoCalc_measured':False,'results':results})


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','benchmark']);p.add_argument('--root',type=Path,default=ROOT/'server-results');a=p.parse_args();torch.set_num_threads(3)
    if a.action=='prepare':prepare(a.root)
    elif a.action=='verify':verify(a.root)
    else:benchmark(a.root)
