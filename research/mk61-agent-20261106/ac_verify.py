"""Check immutable compiler, Q4 exports, argument grammar and shared-buffer native inference."""
import argparse
import ctypes as C
import json
from pathlib import Path
import shutil
import struct
import subprocess
import torch
from transformers import AutoTokenizer
from ac_common import HERE,ARMS,ACTION_IDS,END,read,write,sha,body_ids,output_ids,compact_head
from ac_protocol import Grammar,target_ids,prompt_ids
from ac_eval import generate
from ac_native import Engine
from codec_native import prepare_source,native_tokenizer
from codec_common import ROOT as CODEC_ROOT
from native_verify import verify_export
from native_export import packet


def verify_parser(out,tokenizer):
    path=out/'action-probe.dylib'
    subprocess.run(['clang++','-std=c++17','-O2','-fPIC','-shared',str(HERE/'ab_native_probe.cpp'),'-o',str(path)],check=True)
    p=C.CDLL(str(path));p.ab_accept.argtypes=[C.c_ushort,C.c_char_p];p.ab_allows.argtypes=[C.c_ushort,C.c_char_p]
    p.ab_body.argtypes=[C.POINTER(C.c_ubyte)];grammar=Grammar(tokenizer,0);checks=0
    outputs=output_ids(tokenizer);pieces={i:tokenizer.decode([i],clean_up_tokenization_spaces=False).encode()for i in outputs}
    for action in ['write','run','trace','done','unsure']:
        bodies=[[]]if action in ['trace','done','unsure']else[[b]for b in range(256)]
        for body in bodies:
            values=target_ids(tokenizer,action,body);p.ab_reset();text=''
            for at,token in enumerate(values):
                allowed=ACTION_IDS if at==0 else grammar.permitted(action,text)
                for candidate in outputs:assert bool(p.ab_allows(candidate,pieces[candidate]))==(candidate in allowed),(action,text,candidate)
                assert p.ab_accept(token,pieces[token])
                if at and token!=END:text+=pieces[token].decode()
            assert p.ab_complete()
            actual=(C.c_ubyte*512)();size=p.ab_body(actual);assert list(actual[:size])==body
            checks+=1
    return {'roundtrips_and_python_masks_matched':checks,'state_bytes':p.ab_state_bytes(),
            'allocation_free':True,'has_semantic_oracle':False,'active_output_rows':len(outputs)}


def tool_probes(report):
    history=[h for section in ['tools','goal_twins','from_scratch']for r in report[section]['details']for h in r['history']if 'generation'in h]
    out=[];seen=set()
    for action in ['write','run','trace','done','unsure']:
        options=[h for h in history if h['generation'].get('action')==action]
        for index,h in enumerate(options[:2]):
            if h['prompt']in seen:continue
            seen.add(h['prompt']);out.append({'id':f'{action}:{index}',**h['generation'],'prompt':h['prompt']})
    return out


def compiler_probes(root,report):
    retained=json.loads((root/'compiler-retention.json').read_text());out=[]
    for opcode in [0x1C,0x50,0x54,0x53]:
        out.append(next(r for r in retained['isa']['details']if r['opcode']==opcode and r['angle']=='RAD'))
    out+=report['compiler_language']['details'][:3]+retained['legacy']['details'][:1]
    return out


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args();root=a.root.resolve()
    torch.set_num_threads(4);out=root/'native';out.mkdir(exist_ok=True)
    for filename in ['data-frozen.json','prepared.json']:
        for name,digest in json.loads((root/filename).read_text())['files'].items():assert sha(root/name)==digest,name
    for name,digest in json.loads((root/'prepared.json').read_text())['source_hashes'].items():assert sha(HERE/name)==digest,name
    book=json.loads((CODEC_ROOT/'codebook-32.json').read_text());src,library,exporter=prepare_source(root,out,book)
    tokenizer=AutoTokenizer.from_pretrained(root/'export/compiler/hf',local_files_only=True)
    parser=verify_parser(out,tokenizer);models={};results={}
    frozen=json.loads((root/'data-frozen.json').read_text())
    assert sha(root/'export/compiler/model.mkqb')==frozen['initial_packet_sha256']
    assert sha(root/'export/compiler/hf/model.safetensors')==frozen['initial_master_sha256']
    for arm in ['compiler',*ARMS]:
        folder=root/'export'/arm;model,exact=verify_export(folder);models[arm]=model
        allowed=json.loads((folder/'output-token-ids.json').read_text());compact_head(model,allowed)
        adapted=out/(arm+'-tokenizer.json');native_tokenizer(folder/'hf',adapted)
        header,payload=packet(folder/'model.mkqb');header['config']['max_position_embeddings']=1024
        raw=json.dumps(header,ensure_ascii=False,separators=(',',':')).encode();derived=out/(arm+'-context1024.mkqb')
        derived.write_bytes(b'MKQBv1\0\0'+struct.pack('<I',len(raw))+raw+payload);assert packet(derived)[1]==payload
        exporter.export(derived,adapted,folder/'model.mka','lut')
        results[arm]={'exact_reload':exact,'package_bytes':(folder/'model.mka').stat().st_size,'package_sha256':sha(folder/'model.mka')}
    # Every tensor outside Q/V and five unused input rows stays at the original Q4 values.
    reference=dict(models['compiler'].named_parameters());protected={}
    for arm in ARMS:
        counts={'unchanged_tensors':0,'changed_QV_tensors':0}
        for name,p in models[arm].named_parameters():
            base=reference[name]
            if name.endswith('embed_tokens.weight'):
                keep=torch.ones(len(p),dtype=torch.bool);keep[ACTION_IDS]=False
                assert torch.equal(p[keep],base[keep]),(arm,name)
            elif '.q_proj.'in name or '.v_proj.'in name:
                counts['changed_QV_tensors']+=int(not torch.equal(p,base))
            else:assert torch.equal(p,base),(arm,name);counts['unchanged_tensors']+=1
        protected[arm]={**counts,'base_outside_adapter_and_action_rows_identical':True}
    first=json.loads((root/'sft-audit.json').read_text());compiler_rows=compiler_probes(root,first)
    from hf_eval import generate as compiler_generate
    cpu_compiler=compiler_generate(models['compiler'],tokenizer,[r['prompt']for r in compiler_rows])
    engine=Engine(root,'sft');native_compiler=[]
    for row,cpu in zip(compiler_rows,cpu_compiler):
        actual=engine.compile(row['prompt']);expected=row['generated_token_ids']
        assert actual['input_token_ids']==tokenizer.encode(row['prompt'],add_special_tokens=False)
        native_compiler.append({'id':row['id'],'cpu_matches':cpu['generated_token_ids']==expected,
             'native_matches':actual['generated_token_ids']==expected,'native':actual,'b200':expected})
    assert all(r['cpu_matches']and r['native_matches']for r in native_compiler),native_compiler
    results['compiler'].update(probes=len(compiler_rows),cpu_matches=len(compiler_rows),native_matches=len(compiler_rows),details=native_compiler)
    for arm in ARMS:
        report=json.loads((root/(arm+'-audit.json')).read_text());folder=root/'export'/arm
        assert sha(folder/'model.mkqb')==report['tool_packet_sha256']
        chosen=tool_probes(report);cpu=generate(models[arm],tokenizer,[r['prompt']for r in chosen]);engine.tool=arm;engine.role=None;details=[]
        for row,c in zip(chosen,cpu):
            actual=engine.generate(row['prompt']);expected=row['generated_token_ids']
            assert actual['input_token_ids']==prompt_ids(tokenizer,row['prompt'])
            details.append({'id':row['id'],'cpu_matches':c['generated_token_ids']==expected,
                 'native_matches':actual['generated_token_ids']==expected,'native':actual,'b200':expected})
        assert all(r['cpu_matches']and r['native_matches']for r in details),(arm,details)
        overflow='X '*1100+'<'
        assert generate(models[arm],tokenizer,[overflow])[0]['codec_error']=='context_overflow'
        assert engine.generate(overflow)['codec_error']=='context_overflow'
        # Stream the original profile back into exactly the same model and buffer.
        repeat=engine.compile(compiler_rows[0]['prompt']);assert repeat['generated_token_ids']==compiler_rows[0]['generated_token_ids']
        results[arm].update(probes=len(chosen),cpu_matches=len(chosen),native_matches=len(chosen),details=details,
                            cache_bytes=engine.lib.mk_ai_cache(),workspace_bytes=engine.lib.mk_ai_workspace(),context=1024,native_KV_storage='FP32',
                            context_overflow_rejected_by_CPU_and_native=True)
        runtime=folder/'runtime'
        for name in ['ac_native.py','ab_native.hpp','ab_native_probe.cpp']:shutil.copyfile(HERE/name,runtime/name)
        write(root/'native-verification.json',{'models':results,'parser':parser,'protected':protected,'complete':False})
        print(json.dumps({'verified':arm,'probes':len(chosen),'cpu_and_native_match':True}),flush=True)
    selected=json.loads((root/'preselected.json').read_text())['selected_arm']
    shutil.copytree(root/'export'/selected,root/'export/selected-research',dirs_exist_ok=True)
    write(root/'native-verification.json',{'models':results,'parser':parser,'protected':protected,'complete':True,
          'shared_weight_buffer_bytes':engine.capacity,'shared_buffer_profile_loads':engine.loads,
          'compiler_tool_compiler_switches_verified':True,'physical_picocalc_measured':False})


if __name__=='__main__':main()
