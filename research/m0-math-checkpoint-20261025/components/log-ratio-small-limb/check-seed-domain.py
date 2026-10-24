"""Exhaust the complete new finite seed domain with independent uint128 division."""
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
W=Path(__file__).resolve().parent
ROOT=W.parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from check_stm32_vectors import ElfImage
e=ElfImage(W/'candidate.elf')
n=next(n for n in e.symbols if 'log10_table' in n)
a=e.symbols[n]
s=next(s for s in e.named_sections.values() if s[3]<=a<s[3]+s[5])
data=e.bytes_at(s);start=a-s[3];reciprocals=[]
for i in range(1024):
    row=struct.unpack_from('<4I',data,start+16*i)
    r=(row[1]<<32)|(row[0]&~63)
    assert r==((1<<75)//(2049+2*i))&~63
    reciprocals.append(r)
(W/'reciprocals.bin').write_bytes(struct.pack('<1024Q',*reciprocals))
source=r'''#include <cstdint>
#include <cstdio>
#include <cstdlib>
using U=uint64_t;
using Wide=__uint128_t;
static U mix(U h,U x) {return (h^x)*UINT64_C(1099511628211);}
int main(int argc,char**argv) {
 if(argc!=2)return 2;
 FILE*input=fopen(argv[1],"rb");if(!input)return 3;
 U table[1024];if(fread(table,sizeof(U),1024,input)!=1024)return 4;fclose(input);
 U cases=0,histogram[5]={},digest=UINT64_C(1469598103934665603);
 uint32_t max_limb=0,max_r=0,max_den=1;
 for(uint32_t i=0;i<1024;++i) {
  const uint32_t den=2049+2*i;const U reciprocal=table[i];
  const uint32_t rl=uint32_t(reciprocal),rh=uint32_t(reciprocal>>32);
  for(uint32_t factor=0;factor<=512;++factor) {
   const uint32_t a0=(rl&65535U)*factor;
   const uint32_t a1=(rl>>16)*factor+(a0>>16);
   const uint32_t a2=(rh&65535U)*factor+(a1>>16);
   const uint32_t a3=(rh>>16)*factor+(a2>>16);
   for(auto x:{a0,a1,a2,a3})if(x>max_limb)max_limb=x;
   const U base=(U(((a2>>14)&3U)|(a3<<2))<<32)|
       uint32_t(((a0&65535U)>>14)|((a1&65535U)<<2)|(a2<<18));
   if(base!=U((Wide(factor)*reciprocal)>>14))return 5;
   if(factor==512 && base!=(reciprocal>>5))return 6;
   for(int32_t ell=-64;ell<=64;++ell) {
    const int64_t signed_delta=int64_t(U(factor)<<32)+ell;
    if(signed_delta<0 || U(signed_delta)>(U(1)<<41))continue;
    const U delta=U(signed_delta);
    if(uint32_t(uint32_t(delta)+64U)>128U)return 7;
    const uint32_t magnitude=ell<0?uint32_t(-ell):uint32_t(ell);
    const uint32_t low=(rh>>14)*magnitude+(((rh&16383U)*magnitude)>>14);
    if(low!=U((Wide(rh)*magnitude)>>14))return 8;
    const U seed=ell<0?base-U(low+2U):base+low;
    const Wide exact_numerator=Wide(delta)<<29;
    const U exact=U(exact_numerator/den);
    if(seed>exact || exact-seed>4)return 9;
    const Wide remainder=exact_numerator-Wide(seed)*den;
    if(remainder>=5*den)return 10;
    uint32_t r=(uint32_t(delta)<<29)-uint32_t(seed)*den;
    if(r!=remainder)return 11;
    if(U(r)*max_den>U(max_r)*den) {max_r=r;max_den=den;}
    uint32_t rest=r,correction=0;
    for(uint32_t bit=4;bit;bit>>=1) {
     if(rest>=bit*den) {rest-=bit*den;correction+=bit;}
    }
    if(seed+correction!=exact || rest>=den)return 12;
    histogram[exact-seed]++;cases++;
    digest=mix(mix(mix(digest,delta),den),seed);
   }
  }
 }
 printf("{\"status\":\"PASS_ENTIRE_SMALL_LOW_LIMB_SEED_DOMAIN\",\"pairs\":%llu,\"denominators\":1024,\"factors\":513,\"signed_low_limbs\":129,\"max_limb_intermediate\":%u,\"max_residue_numerator\":%u,\"max_residue_denominator\":%u,\"floor_correction_histogram\":[%llu,%llu,%llu,%llu,%llu],\"digest_fnv64\":\"%016llx\",\"hardware_accessed\":false}\n",
 (unsigned long long)cases,max_limb,max_r,max_den,
 (unsigned long long)histogram[0],(unsigned long long)histogram[1],(unsigned long long)histogram[2],(unsigned long long)histogram[3],(unsigned long long)histogram[4],(unsigned long long)digest);
 return 0;
}
'''
# std::initializer_list is only a host test convenience, never runtime code.
source=source.replace('#include <cstdlib>','#include <cstdlib>\n#include <initializer_list>')
(W/'seed-domain.cpp').write_text(source)
command=['/usr/bin/clang++','-O2','-std=c++17',str(W/'seed-domain.cpp'),'-o',str(W/'seed-domain')]
subprocess.run(command,check=True)
completed=subprocess.run([str(W/'seed-domain'),str(W/'reciprocals.bin')],check=True,capture_output=True,text=True)
r=json.loads(completed.stdout)
assert r['pairs']==67634176
r.update(source_sha256=hashlib.sha256((W/'native_eabi_m0_log70_center.inc').read_bytes()).hexdigest(),
         candidate_ELF_sha256=hashlib.sha256((W/'candidate.elf').read_bytes()).hexdigest(),
         host_test_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
         reciprocal_bytes_sha256=hashlib.sha256((W/'reciprocals.bin').read_bytes()).hexdigest(),
         compiler_command=command,not_ARM_execution=True)
(W/'seed-domain-proof.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r,indent=2))
