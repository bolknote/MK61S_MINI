from pathlib import Path
import json,hashlib,shutil,subprocess,struct
R=Path('/Users/bolk/Projects/MK61S_MINI');B=Path(__file__).resolve().parent
T=R/'.build/mk61-agent-20261106/harness-debug-v3/server-results';M=T/'export/selected-budget';S=R/'.build/mk61ai/swar-v5/source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((M/'manifest.json').read_text());info=json.loads((M/'native-info.json').read_text())
assert manifest['packed_sha256']==sha(M/'model.mkqb')=='1b53d0e26f8156141f47a877393d2a617e13014fbe36d7d8cf1ca907a6d1647c'
assert info['package_sha256']==sha(M/'model.mka')=='7355022789e1ea8632901d25b957cd0d4b9bda67ea65505d50b3c920c90bf3f0'
model=B/'model';model.mkdir(exist_ok=True)
for n in ['model.mka','model.mkqb','manifest.json','native-info.json','output-token-ids.json','protocol.json']:
 shutil.copyfile(M/n,model/n)
subprocess.run(['python3',str(S/'tools/apps/mk61ai/repack_q4.py'),str(model/'model.mka'),str(model/'model-nibble.mka')],check=True,stdout=(B/'repack.json').open('w'))
src=B/'source';src.mkdir(exist_ok=True)
for n in ['mk61_ai_model.cpp','mk61_ai_model.hpp','mk61_ai_linear.cpp','mk61_ai_linear.hpp','mk61_ai_swar.hpp','mk61_ai_tokenizer.cpp','mk61_ai_kernels.c','mk61_ai_kernels.h','block_read.hpp']:
 shutil.copyfile(S/'code'/n,src/n)
shutil.copyfile(S/'tests/mk61_ai_model_probe.cpp',src/'probe.cpp')
shutil.copyfile(R/'research/mk61-agent-20261106/codec_native_bridge.hpp',src/'codec_native_bridge.hpp')
with (src/'probe.cpp').open('a') as f:f.write('''
#include "codec_native_bridge.hpp"
namespace { std::vector<unsigned char> quality_mask; int quality_mode=3; }
extern "C" void codec_set_mask(const unsigned short *ids,unsigned n) {
 quality_mask.assign(model.config().vocab,0);
 for(unsigned i=0;i<n;++i)if(ids[i]<quality_mask.size())quality_mask[ids[i]]=1;
 mk61ai::ComputeExecution execution;execution.kernel=mk61ai::LinearKernel::SRAM;execution.filter_head=true;model.execution(execution);
}
extern "C" void codec_set_mode(int mode) {quality_mode=mode;}
extern "C" int codec_forward(unsigned short token,int output,unsigned short *best,float *logits) {
 return int(model.forward(token,output,*best,service,nullptr,static_cast<mk61ai::Arithmetic>(quality_mode),logits,
 [](void*,std::uint16_t id){return quality_mask[id]!=0;},nullptr));
}
extern "C" int codec_encode(const char* text,unsigned short* out,unsigned cap,unsigned* used) {
 return int(mk61research::encode_h32(model,text,out,cap,*used));
}
''')
subprocess.run(['clang','-std=c11','-O2','-ffp-contract=off','-fPIC','-c',str(src/'mk61_ai_kernels.c'),'-o',str(B/'kernels.o')],check=True)
subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I'+str(src),*[str(src/n)for n in ['mk61_ai_model.cpp','mk61_ai_linear.cpp','mk61_ai_tokenizer.cpp','probe.cpp']],str(B/'kernels.o'),'-o',str(B/'quality-probe.dylib')],check=True)
# Freeze the current trained prompt, macro assembler, real emulator interface and grading semantics.
py=B/'runtime';py.mkdir(exist_ok=True)
for n in ['hf_runtime.py','ha_runtime.py','ha_protocol.py','full_isa_vm.py','full_isa_protocol.py','full_isa_math.py','emulator.py','tasks.py']:
 shutil.copyfile(R/'research/mk61-agent-20261106'/n,py/n)
vm=B/'emulator';vm.mkdir(exist_ok=True);core=vm/'core-source';core.mkdir(exist_ok=True)
old=R/'.build/mk61-agent-20261106/full-isa-v1/core-source'
assert (old/'mk61emu_core.cpp').exists()
for p in old.rglob('*'):
 if p.is_file():q=core/p.relative_to(old);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
shutil.copyfile(R/'research/mk61-agent-20261106/full_isa_bridge.cpp',py/'full_isa_bridge.cpp')
# It supplies symbols shared with the emulator bridge.
shutil.copyfile(R/'research/mk61-agent-20261106/core_bridge.cpp',py/'core_bridge.cpp')
sets=B/'cases';sets.mkdir(exist_ok=True)
for n in ['fresh.jsonl','fresh-tool-seeds.jsonl','isa-audit.jsonl','legacy-development.jsonl','observed-user-reproductions.jsonl']:
 shutil.copyfile(T/n,sets/n)
doc=[json.loads(s)for s in (sets/'isa-audit.jsonl').read_text().splitlines()if s.strip()];doc=[x for x in doc if x['kind']=='primitive'and x.get('catalog_risk')=='documented'];assert len(doc)==648
(sets/'documented648.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in doc))
# Use exact declared native replay probes before interpreting any quality scores.
report=json.loads((T/'results/active-best.json').read_text());pool={x['id']:x for panel in ['isa','language','observed_user_reproductions']for x in report[panel]['details']}
for kind in ['trace','patch','run','done']:
 h=next((h for panel in ['tools','tools_gated']for t in report[panel]['details']for h in t['history']if h.get('kind')==kind and'prompt'in h),None)
 if h:pool['tool:'+kind]={'id':'tool:'+kind,**h}
probes=[]
for row in info['details']:
 found=pool[row['id']];assert found.get('generated_token_ids')==row['tokens'],row['id'];probes.append(dict(id=row['id'],prompt=found['prompt'],tokens=row['tokens'],input_tokens=row['input_tokens']))
(B/'probes13.json').write_text(json.dumps(probes,ensure_ascii=False,indent=2)+'\n')
frozen=dict(status='FROZEN_BEFORE_RUN',model='Flourish3M/harness-debug-v3/selected-budget',selected_step=manifest['selected_step'],parameters=manifest['parameters'],context=1024,input_vocab=8224,output_tokens=40,model_mka_sha256=sha(model/'model.mka'),model_nibble_sha256=sha(model/'model-nibble.mka'),model_packet_sha256=sha(model/'model.mkqb'),source_pins={str(p.relative_to(B)):sha(p)for folder in [src,py,core,model,sets]for p in sorted(folder.rglob('*'))if p.is_file()},library_sha256=sha(B/'quality-probe.dylib'),criteria=['first reproduce all13 native/B200 LUT probes; else do not interpret quality','all282 fresh synthesis tasks,648 documented command probes,98 legacy and27 user reproductions count','all72 debugging seeds and48 fresh from-scratch sessions; gate has no semantic oracle','same prompt/protocol/40-token head/context/greedy/max512/6turns for3 arithmetic modes','all public and hidden cases independently graded; no hidden values passed to Session or inference','do not change default if any baseline-solved task is lost or false DONE increases','no training, device I/O or best-of runs'])
(B/'manifest.json').write_text(json.dumps(frozen,indent=2)+'\n');print(json.dumps({k:frozen[k]for k in ['status','model','selected_step','parameters','context','input_vocab','output_tokens','criteria']},indent=2))
