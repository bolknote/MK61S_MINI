from pathlib import Path
import numpy as np,json,struct,zlib,hashlib,shutil,subprocess
B=Path(__file__).resolve().parent;src=B/'weights-source';shutil.copytree(B/'source',src,dirs_exist_ok=True)
raw=(B/'model/model-nibble.mka').read_bytes();h=struct.unpack_from('<32I',raw);outputs={k:bytearray(raw)for k in ['lns','apot']};hist=np.zeros(16,dtype=np.int64);stats={k:[0.,0.,0,0.]for k in outputs}
# Signed4-bit code, one alias for zero: seven nonzero magnitudes per sign.
# APoT B=3 magnitude set follows the authors' signed4-bit construction before shared normalization.
sets={'lns':np.array([0,1,2,4,8,16,32,64],dtype=np.float64),'apot':np.array([0,1,2,3,4,6,8,10],dtype=np.float64)}
for tensor in range(2+11*h[4]):
 at=h[15]+32*tensor;rows,cols,bits,grid,offset,scales,nbytes,nscales=struct.unpack_from('<8I',raw,at)
 if bits!=4:continue
 assert grid==0
 packed=np.frombuffer(raw,dtype=np.uint8,count=nbytes,offset=offset);u=np.empty(nbytes*2,dtype=np.uint8);u[0::2]=packed&15;u[1::2]=packed>>4;hist+=np.bincount(u,minlength=16)
 q=u.astype(np.float64).reshape(-1,32)-8;scale=np.frombuffer(raw,dtype='<f2',count=nscales//2,offset=scales).astype(np.float64);weights=q*scale[:,None];maxabs=np.max(np.abs(weights),axis=1)
 for name,levels in sets.items():
  newscale=(maxabs/levels[-1]).astype('<f2');den=newscale.astype(np.float64);norm=np.divide(np.abs(weights),den[:,None],out=np.zeros_like(weights),where=den[:,None]!=0)
  index=np.abs(norm[:,:,None]-levels[None,None,:]).argmin(axis=2).astype(np.uint8);codes=index|((weights<0).astype(np.uint8)<<3)
  reconstructed=levels[index]*den[:,None]*np.where(weights<0,-1,1);delta=weights-reconstructed
  stats[name][0]+=float((delta*delta).sum());stats[name][1]+=float((weights*weights).sum());stats[name][2]+=weights.size;stats[name][3]=max(stats[name][3],float(np.abs(delta).max()))
  v=codes.reshape(-1);data=(v[0::2]|(v[1::2]<<4)).astype(np.uint8).tobytes();blob=outputs[name];blob[offset:offset+nbytes]=data;blob[scales:scales+nscales]=newscale.tobytes();struct.pack_into('<I',blob,at+12,512 if name=='lns' else 1024)
for name,blob in outputs.items():
 struct.pack_into('<I',blob,116,zlib.crc32(blob[128:]));struct.pack_into('<I',blob,124,zlib.crc32(blob[:124]));(B/'model'/('model-'+name+'.mka')).write_bytes(blob)
p=hist/hist.sum();entropy=float(-(p[p>0]*np.log2(p[p>0])).sum());code_bytes=int(hist.sum())//2;saving=code_bytes*(1-entropy/4)
result=dict(q4_coefficients=int(hist.sum()),q4_codes_bytes=code_bytes,histogram=hist.tolist(),entropy_bits_per_code=entropy,ideal_zero_order_code_saving_bytes=saving,ideal_whole_file_saving_fraction=saving/len(raw),warning='ideal entropy bound, excludes coding tables, alignment and decodeCPU; not a measured compressor',weights={k:dict(relative_l2_squared=v[0]/v[1],rmse=(v[0]/v[2])**.5,max_abs_weight_delta=v[3],parameters=v[2],levels=sets[k].tolist(),effective_signed_levels=15,model_sha256=hashlib.sha256(outputs[k]).hexdigest())for k,v in stats.items()})
(B/'weight-grid-report.json').write_text(json.dumps(result,indent=2)+'\n')
helper='''#pragma once
#include <cstdint>
inline int research_coefficient(unsigned grid,unsigned u) {
 static constexpr int lns[8]={0,1,2,4,8,16,32,64};
 static constexpr int apot[8]={0,1,2,3,4,6,8,10};
 const int magnitude=(grid&1024)?apot[u&7]:lns[u&7];return(u&8)?-magnitude:magnitude;
}
''';(src/'research_codebook.hpp').write_text(helper)
p=src/'mk61_ai_model.cpp';s=p.read_text().replace('#include "mk61_ai_model.hpp"','#include "mk61_ai_model.hpp"\n#include "research_codebook.hpp"')
s=s.replace('(t.grid & ~256U)', '(t.grid & ~(256U|512U|1024U))')
needle='    return ((t.grid & 1)';assert needle in s;s=s.replace(needle,'    if(t.grid&1536U)return float(research_coefficient(t.grid,u))*scale;\n'+needle,1);p.write_text(s)
p=src/'mk61_ai_linear.cpp';s=p.read_text().replace('#include "mk61_ai_linear.hpp"','#include "mk61_ai_linear.hpp"\n#include "research_codebook.hpp"');needle='MK61_AI_INLINE void dispatch(LinearBatch &b) {'
fn='''
MK61_AI_INLINE void research_grid(LinearBatch &b) {
 if(b.arithmetic!=Arithmetic::FLOAT32 || b.bits!=4){b.status=ModelStatus::FORMAT;return;}
 for(unsigned r=0;r<b.rows;++r){float value=0;const auto*w=b.weights+r*b.columns/2;const auto*s=b.scales+r*b.columns/16;
  for(unsigned g=0;g<b.columns/32;++g){const float scale=half(std::uint16_t(s[2*g])|(std::uint16_t(s[2*g+1])<<8));
   for(unsigned j=0;j<32;++j){const unsigned col=32*g+j;const unsigned u=unpack(w,col,4,false);value+=b.input[col]*(float(research_coefficient(b.grid,u))*scale);}}
  if(!std::isfinite(value)){b.status=ModelStatus::NUMERIC;return;}b.output[r]=value;
 }
}
''';s=s.replace(needle,fn+needle);s=s.replace('  b.status = ModelStatus::OK;','  b.status = ModelStatus::OK;\n  if(b.grid&1536U)return research_grid(b);');p.write_text(s)
p=src/'probe.cpp';s=p.read_text().replace(' default:\n  if(quality_profile>=30', ' default:\n  if(quality_profile>=100)q.mode=A::FLOAT32;\n  else if(quality_profile>=30');p.write_text(s)
subprocess.run(['clang','-std=c11','-O2','-ffp-contract=off','-fPIC','-c',str(src/'mk61_ai_kernels.c'),'-o',str(B/'weights-kernels.o')],check=True)
subprocess.run(['clang++','-std=c++17','-O2','-ffp-contract=off','-fPIC','-shared','-I'+str(src),*[str(src/n)for n in ['mk61_ai_model.cpp','mk61_ai_linear.cpp','mk61_ai_tokenizer.cpp','probe.cpp']],str(B/'weights-kernels.o'),'-o',str(B/'weights-probe.dylib')],check=True)
print(json.dumps(result,indent=2))
