#!/usr/bin/env python3
import hashlib,json,statistics,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from exact_oracle import root_oracle
GROUPS=('ln_full_fused','texture_pop','audio_resample','sqrt_new_cpu_full','sqrt_new_interp_full','rsqrt_new_cpu_full','rsqrt_new_interp_full')
VARIANTS={'lookup':(0,1,4096),'pop':(1,2,32),'sqrt':(3,2,4096),'rsqrt':(5,2,4096)}

def decode(raw,*,variant,physical=True,expected_rounds=7,expected_samples=None):
 first,count,samples=VARIANTS[variant]
 if expected_samples is not None:samples=expected_samples
 assert len(raw)>=256
 h=struct.unpack_from('<14I',raw)
 magic,version,size,rows,rounds,ns,checks,failures,status,core,control,ipsr,primask,restored=h
 assert (magic,version,size,rows,rounds,ns,checks)==(0x324f4649,4,len(raw),6*count,expected_rounds,samples,96*count),h
 assert failures==0 and status==1 and core==0 and not control&1 and ipsr==primask==0 and restored==1,h
 before=struct.unpack_from('<7I',raw,56);after=struct.unpack_from('<7I',raw,84)
 assert before==after,'Clock changed'
 ctrl,div,selected,cs,pwr,fb,prim=before
 ref=cs&63;post1=(prim>>16)&7;post2=(prim>>12)&7
 assert ctrl&1 and not ctrl&0xe0 and selected==2 and cs&(1<<31) and not pwr&0x29
 assert ref and post1 and post2 and div
 assert 12000000*(fb&4095)*256==125000000*ref*post1*post2*div,before
 assert raw[112:128]==raw[128:144] and raw[144:200]==raw[200:256],'Peripheral restore mismatch'
 stride=48+40*rounds;assert len(raw)==256+rows*stride
 result=[]
 for i in range(rows):
  off=256+i*stride;g,mode,kind=struct.unpack_from('<3I',raw,off)
  assert (g,mode,kind)==(first+i//6,i//3%2,i%3)
  x,n,aa,bb=struct.unpack_from('<4Q',raw,off+16);assert aa==bb,(g,kind,hex(aa),hex(bb))
  if g in (3,4,5,6):assert aa==root_oracle(x,g>=5)
  if g in (1,2):assert n==(32,256,1024)[kind]
  times=[list(struct.unpack_from('<4I',raw,off+48+16*r)) for r in range(rounds)]
  empty=[list(struct.unpack_from('<2I',raw,off+48+16*rounds+8*r)) for r in range(rounds)]
  hashes=[list(struct.unpack_from('<4I',raw,off+48+24*rounds+16*r)) for r in range(rounds)]
  pairs=[]
  for r in range(rounds):
   assert len(set(hashes[r]))==1,('A/B output drift',g,mode,kind,r)
   a=(times[r][0]+times[r][3])/2;b=(times[r][1]+times[r][2])/2
   if r&1:a,b=b,a
   items=samples*(n if g in (1,2) else 1)
   pairs.append(dict(cpu_total_us=a,candidate_total_us=b,cpu_us_per_item=a/items,candidate_us_per_item=b/items,delta_us_per_item=(b-a)/items))
  result.append(dict(group=GROUPS[g],mode='per_call_transaction' if mode else 'prepared_batch',input=kind,
    a=hex(x),block_items=n if g in (1,2) else 1,result_a=hex(aa),result_b=hex(bb),raw_us=times,
    empty_us=empty,checksums=hashes,rounds=pairs))
 return dict(status='PASS',variant=variant,result_schema=4,hardware_verified=physical,physical_timing=physical,
   rows=rows,checks=checks,rounds=rounds,samples=samples,clock_hz=125000000,
   output_sha256=hashlib.sha256(raw).hexdigest(),interpolator_state_restored=True,divider_state_restored=True,
   timing='Scalar: function+input loop+checksum. POP/audio: complete block call including output stores; validation/hash after stop timer. Setup/restore per block in transaction mode. IRQs enabled; no empty subtraction.',results=result)

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('raw',type=Path);p.add_argument('--variant',choices=VARIANTS,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.write_text(json.dumps(decode(a.raw.read_bytes(),variant=a.variant),indent=2)+'\n')
