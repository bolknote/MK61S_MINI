"""Exact Q4 reload, protected input rows, and C++ action/semantic-head verification."""
import argparse
import ctypes as C
import json
from pathlib import Path
import shutil
import struct
import torch
from transformers import AutoTokenizer
from ah_common import HERE,OLD,ARMS,ACTION_IDS,CORRECT_IDS,read,write,sha,output_ids,compact_head
from ah_eval import generate
from ah_native import Engine,prepare_source,MAX_INPUT_BYTES
from ac_verify import verify_parser
from ac_protocol import prompt_ids
from codec_native import native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_export import packet
from native_verify import verify_export


def probes(report,threshold):
    values=[]
    for part in ['main','skills','goals','from_scratch']:
        for panel in report[part].values():
            if not isinstance(panel,dict)or'details'not in panel:continue
            for row in panel['details']:
                values += [h for h in row['history']if'prompt'in h and'generation'in h and h.get('profile')!='compiler']
    selected=[];seen=set()
    for action in ['write','run','trace','done','unsure']:
        for h in [h for h in values if h['generation'].get('action')==action][:2]:
            if h['prompt']in seen:continue
            seen.add(h['prompt']);selected.append({'id':action+':'+str(len(selected)),**h['generation'],'prompt':h['prompt']})
    near=sorted([h for h in values if h['generation'].get('correctness_margin')is not None and not h['generation'].get('codec_error')],
                key=lambda h:abs(h['generation']['correctness_margin']-threshold))
    for h in near[:2]:
        if h['prompt']not in seen:selected.append({'id':'threshold:'+str(len(selected)),**h['generation'],'prompt':h['prompt']});seen.add(h['prompt'])
    return selected


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve();out=root/'native';out.mkdir(exist_ok=True)
    torch.set_num_threads(4)
    for name in ['data-frozen.json','prepared.json']:
        for file,digest in json.loads((root/name).read_text())['files'].items():assert sha(root/file)==digest,file
    for file,digest in json.loads((root/'prepared.json').read_text())['source_hashes'].items():assert sha(HERE/file)==digest,file
    prepare_source(root,out,json.loads((CODEC_ROOT/'codebook-32.json').read_text()))
    # Obtain the exporter from the same fixed source without changing the model.
    import importlib.util
    spec=importlib.util.spec_from_file_location('ae_native_exporter',out/'source/export_model.py');exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)
    tokenizer=AutoTokenizer.from_pretrained(root/'export/compiler/hf',local_files_only=True);parser=verify_parser(out,tokenizer)
    p=C.CDLL(str(out/'action-probe.dylib'));p.ab_allows.argtypes=[C.c_ushort,C.c_char_p]
    for token in CORRECT_IDS:p.ab_reset();assert not p.ab_allows(token,tokenizer.decode([token]).encode())
    frozen=json.loads((root/'data-frozen.json').read_text());assert sha(root/'export/compiler/model.mkqb')==frozen['compiler_packet_sha256']
    source,_=verify_export(OLD/'export/sft');reference=source.get_input_embeddings().weight.detach().clone();del source
    profiles=[*ARMS,*[a+'-terminal'for a in ARMS]]
    results={};models={};protected={}
    for arm in ['compiler',*profiles]:
        folder=root/'export'/arm;model,exact=verify_export(folder);models[arm]=model;compact_head(model,json.loads((folder/'output-token-ids.json').read_text()))
        if arm!='compiler':
            keep=torch.ones(len(reference),dtype=torch.bool);keep[ACTION_IDS+CORRECT_IDS]=False
            assert torch.equal(reference[keep],model.get_input_embeddings().weight[keep]);protected[arm]={'rows':int(keep.sum()),'Q4_bit_identical':True}
        native_tokenizer(folder/'hf',out/(arm+'-tokenizer.json'));header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(arm+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        exporter.export(derived,out/(arm+'-tokenizer.json'),folder/'model.mka','lut')
        results[arm]={'exact_reload':exact,'package_bytes':(folder/'model.mka').stat().st_size,'package_sha256':sha(folder/'model.mka')}
    engine=Engine(root,'replay');retained=json.loads((OLD/'compiler-retention.json').read_text());compiler=[]
    for opcode in [0x1C,0x50,0x53,0x54]:compiler.append(next(r for r in retained['isa']['details']if r['opcode']==opcode and r['angle']=='RAD'))
    compiler+=retained['legacy']['details'][:2]
    from hf_eval import generate as old_generate
    cpu=old_generate(models['compiler'],tokenizer,[r['prompt']for r in compiler]);crows=[]
    for r,c in zip(compiler,cpu):
        native=engine.compile(r['prompt']);assert native['generated_token_ids']==c['generated_token_ids']==r['generated_token_ids']
        assert native['input_token_ids']==tokenizer.encode(r['prompt'],add_special_tokens=False);crows.append({'id':r['id'],'tokens_equal_B200':True})
    results['compiler'].update(probes=len(crows),cpu_matches=len(crows),native_matches=len(crows),details=crows)
    pre=json.loads((root/'preselected.json').read_text());long_text={};longest=0
    for arm in profiles:
        terminal=arm.endswith('-terminal');base=arm.removesuffix('-terminal')
        report=json.loads((root/(base+'/terminal-fresh-audit.json'if terminal else arm+'-fresh-audit.json')).read_text());folder=root/'export'/arm
        assert sha(folder/'model.mkqb')==report['packet_sha256']
        threshold=json.loads((folder/'protocol.json').read_text())['correctness_threshold']
        chosen=probes(report,threshold);cpu=generate(models[arm],tokenizer,[r['prompt']for r in chosen]);engine.tool=arm;engine.role=None;details=[]
        for part in ['main','skills','goals','from_scratch']:
            for panel in report[part].values():
                for r in panel['details']:
                    for h in r['history']:
                        g=h.get('generation',{});text=h.get('prompt')
                        if text and g.get('input_tokens',9999)<1016 and len(text.encode())>2048:long_text[text]=True
        for r,c in zip(chosen,cpu):
            native=engine.generate(r['prompt']);expected=r['generated_token_ids']
            if 'input_token_ids'not in native:
                write(root/'native-incomplete-probe.json',{'arm':arm,'probe':r,'cpu':c,'native':native})
                raise RuntimeError((arm,r['id'],native))
            assert native['input_token_ids']==prompt_ids(tokenizer,r['prompt']);assert native['generated_token_ids']==c['generated_token_ids']==expected,(arm,r['id'])
            margin_error=abs(native['correctness_margin']-r['correctness_margin']);assert margin_error<.01,(arm,r['id'],margin_error)
            same_decision=(native['correctness_margin']>=threshold)==(r['correctness_margin']>=threshold)
            details.append({'id':r['id'],'tokens_equal_B200':True,'margin_error':margin_error,'threshold_decision_equal_B200':same_decision,
                  'native':native,'B200_margin':r['correctness_margin']})
        repeat=engine.compile(compiler[0]['prompt']);assert repeat['generated_token_ids']==compiler[0]['generated_token_ids']
        results[arm].update(probes=len(chosen),cpu_matches=len(chosen),native_matches=len(chosen),details=details,
          threshold_decisions_matched=sum(r['threshold_decision_equal_B200']for r in details))
        results[arm].update(cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace(),context=1024,auxiliary_logits_buffer_bytes=8224*4)
        for name in ['ah_native.py','ac_native.py','ab_native.hpp','ab_native_probe.cpp']:shutil.copyfile(HERE/name,folder/'runtime'/name)
        print(json.dumps({'verified':arm,'probes':len(chosen),'margin_max_error':max(r['margin_error']for r in details)}),flush=True)
    # Regression for the reproduced 797-token/2059-byte failure and other
    # recorded long prefixes; this checks tokenization, not new model answers.
    encoded=(C.c_ushort*1024)();used=C.c_uint()
    for text in long_text:
        assert len(text.encode())<=MAX_INPUT_BYTES
        assert engine.lib.codec_encode(text[:-1].encode(),encoded,1023,C.byref(used))==0
        assert list(encoded[:used.value])+[30]==prompt_ids(tokenizer,text)
        longest=max(longest,len(text.encode()))
    assert engine.lib.codec_encode(b'a'*(MAX_INPUT_BYTES+1),encoded,1023,C.byref(used))!=0
    assert engine.prefill('0 '*1100+'<',True)is None
    shutil.copytree(root/'export'/pre['selected_arm'],root/'export/selected-research',dirs_exist_ok=True)
    write(root/'native-verification.json',{'complete':True,'models':results,'parser':parser,'protected_rows':protected,
        'shared_weight_buffer_bytes':engine.capacity,'compiler_tool_compiler_switches_verified':True,'physical_device_measured':False,
        'long_input_regression':{'prefixes_checked':len(long_text),'max_utf8_bytes_checked':longest,'input_byte_limit':MAX_INPUT_BYTES,
          'over_byte_limit_rejected':True,'over_context_rejected':True,'segment_stack_buffer_bytes':MAX_INPUT_BYTES+1},
        'research_native_sources':{p.name:sha(p)for p in(out/'source').iterdir()if p.is_file()}})


if __name__=='__main__':main()
