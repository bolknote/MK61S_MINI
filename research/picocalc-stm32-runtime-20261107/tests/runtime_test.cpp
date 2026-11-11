#include "stm3_runtime.h"
#include <algorithm>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <random>
#include <vector>
extern "C" uint32_t module_entry(uint32_t,const stm3_api*,stm3_job*);
static uint32_t clock_us=0,increment_us=1;
static uint32_t micros(void*){const auto n=clock_us;clock_us+=increment_us;return n;}
static uint32_t address(void*,const void*){return 0x20003000;}
static uint32_t invoke(void*,uint32_t entry,uint32_t op,const stm3_api*api,stm3_job*j){assert(entry>=0x20003001&&entry<0x20004800);return module_entry(op,api,j);}
static uint32_t get(const uint8_t*p){return uint32_t(p[0])|uint32_t(p[1])<<8|uint32_t(p[2])<<16|uint32_t(p[3])<<24;}
static void put(uint8_t*p,uint32_t n){for(unsigned i=0;i<4;++i)p[i]=uint8_t(n>>(8*i));}
static std::vector<uint8_t> words(std::initializer_list<uint32_t> ns){std::vector<uint8_t>v(4*ns.size());unsigned at=0;for(auto n:ns){put(v.data()+at,n);at+=4;}return v;}
static std::vector<uint8_t> cmd(stm3_runtime&r,uint8_t op,const std::vector<uint8_t>&in={},unsigned error=0){uint8_t out[256];uint16_t n=0;stm3_command(&r,op,in.data(),uint16_t(in.size()),out,&n);assert(n>=4&&get(out)==error);return {out+4,out+n};}
static void reset(stm3_runtime&r){const stm3_backend b={nullptr,micros,address,invoke,0,0};stm3_init(&r,&b);}
static void load(stm3_runtime&r,const std::vector<uint8_t>&p,unsigned commit_error=0){
 cmd(r,STM3_LOAD_BEGIN,words({uint32_t(p.size())}));
 for(unsigned at=0;at<p.size();){unsigned n=std::min<unsigned>(252,p.size()-at);auto block=words({at});block.insert(block.end(),p.begin()+at,p.begin()+at+n);cmd(r,STM3_LOAD_CHUNK,block);at+=n;}
 cmd(r,STM3_LOAD_COMMIT,{},commit_error);
}
static void fix(std::vector<uint8_t>&p){put(p.data()+48,stm3_crc32(p.data()+64,p.size()-64));put(p.data()+60,stm3_crc32(p.data(),60));}
int main(int argc,char**argv){
 assert(argc==2);std::ifstream f(argv[1],std::ios::binary);assert(f);std::vector<uint8_t>package((std::istreambuf_iterator<char>(f)),{});
 stm3_runtime r;reset(r);load(r,package);assert(r.state==STM3_READY&&r.module_id==1);
 const auto*head=(const stm3_header*)package.data();assert(head->reloc_count);
 for(unsigned i=0;i<head->reloc_count;++i){const unsigned at=get(package.data()+64+head->image_bytes+4*i);assert(get(r.arena.bytes+at)==0x20003000+(get(package.data()+64+at)-STM3_LINK_BASE));}
 for(unsigned i=head->image_bytes;i<head->image_bytes+head->bss_bytes;++i)assert(!r.arena.bytes[i]);
 std::mt19937 rng(0x53544d33);unsigned checked=0;
 for(unsigned test=0;test<160;++test){
  const unsigned rows=1+test%16;auto in=words({0x31544451,rows,32});std::vector<int32_t>x(32);std::vector<int64_t>reference(rows);
  for(unsigned c=0;c<32;++c){x[c]=test<16?-32768:test<32?32767:int16_t(rng());in.push_back(uint8_t(x[c]));in.push_back(uint8_t(x[c]>>8));}
  for(unsigned row=0;row<rows;++row)for(unsigned c=0;c<32;c+=2){const unsigned a=rng()&15,b=rng()&15;in.push_back(uint8_t(a|(b<<4)));reference[row]+=(int(a)-8)*int64_t(x[c])+(int(b)-8)*int64_t(x[c+1]);}
  auto block=words({0});block.insert(block.end(),in.begin(),in.end());
  // The wire payload limit needs at most2 writes for the largest vector.
  for(unsigned at=0;at<in.size();){const unsigned n=std::min<unsigned>(252,in.size()-at);auto b=words({at});b.insert(b.end(),in.begin()+at,in.begin()+at+n);cmd(r,STM3_WRITE,b);at+=n;}
  const auto start=cmd(r,STM3_START,words({r.module_id,uint32_t(in.size()),100}));assert(get(start.data())==r.job_id);
  cmd(r,STM3_WRITE,words({0}),STM3_E_STATE);cmd(r,STM3_UNLOAD,{},STM3_E_STATE);
  for(unsigned i=0;i<rows;++i){assert(r.state==STM3_RUNNING);stm3_tick(&r);}assert(r.state==STM3_FINISHED);
  auto out=cmd(r,STM3_READ,words({r.job_id,0,8+4*rows}));assert(get(out.data())==rows&&get(out.data()+4)>0);
  for(unsigned row=0;row<rows;++row){assert(int32_t(get(out.data()+8+row*4))==reference[row]);++checked;}
 }
 cmd(r,STM3_READ,words({r.job_id,UINT32_MAX,4}),STM3_E_SIZE);
 cmd(r,STM3_START,words({r.module_id-1,1,100}),STM3_E_MODULE);
 // Cancel between bounded module steps, without unloading its constants.
 cmd(r,STM3_START,words({r.module_id,332,100}));cmd(r,STM3_CANCEL_JOB,words({r.job_id}));assert(r.state==STM3_CANCELLED);stm3_tick(&r);assert(r.state==STM3_CANCELLED);
 cmd(r,STM3_UNLOAD);assert(r.state==STM3_EMPTY);for(auto b:r.arena.bytes)assert(!b);
 unsigned invalid=0;
 for(unsigned type=0;type<11;++type){
  auto bad=package;unsigned error=STM3_E_FORMAT;
  switch(type){
   case 0:bad.back()^=1;error=STM3_E_CRC;break;
   case 1:bad[60]^=1;error=STM3_E_CRC;break;
   case 2:put(bad.data()+4,2);fix(bad);error=STM3_E_ABI;break;
   case 3:put(bad.data()+56,0x70302);fix(bad);error=STM3_E_ABI;break;
   case 4:put(bad.data()+20,6144);fix(bad);error=STM3_E_SIZE;break;
   case 5:put(bad.data()+24,0);fix(bad);break;
   case 6:put(bad.data()+64+head->image_bytes,head->image_bytes);fix(bad);break;
   case 7:put(bad.data()+32,513);fix(bad);error=STM3_E_SIZE;break;
   case 8:put(bad.data()+44,0);fix(bad);error=STM3_E_SIZE;break;
   case 9:put(bad.data()+52,1);fix(bad);break;
   case 10:put(bad.data()+28,65);fix(bad);error=STM3_E_SIZE;break;
  }
  reset(r);load(r,bad,error);assert(r.state==STM3_FAULT&&r.entry==0);cmd(r,STM3_UNLOAD);++invalid;
 }
 // Check deadline and returned-slice overrun detection independently.
 reset(r);load(r,package);auto in=words({0x31544451,1,32});in.resize(92);auto w=words({0});w.insert(w.end(),in.begin(),in.end());cmd(r,STM3_WRITE,w);cmd(r,STM3_START,words({r.module_id,92,1}));clock_us+=2000;stm3_tick(&r);assert(r.state==STM3_FAULT&&r.error==STM3_E_TIME);cmd(r,STM3_UNLOAD);
 reset(r);load(r,package);cmd(r,STM3_WRITE,w);increment_us=3000;cmd(r,STM3_START,words({r.module_id,92,100}),STM3_E_TIME);assert(r.state==STM3_FAULT);increment_us=1;cmd(r,STM3_UNLOAD);
 // Arbitrary framing/noise must not corrupt state or cross buffers.
 reset(r);for(unsigned i=0;i<60000;++i)stm3_feed(&r,uint8_t(rng()));stm3_feed(&r,0);assert(r.state==STM3_EMPTY);
 for(unsigned n=1;n<=268;++n){std::vector<uint8_t>a(n),encoded(272),decoded(272);for(auto&x:a)x=uint8_t(rng());unsigned e=stm3_cobs_encode(a.data(),n,encoded.data(),encoded.size());assert(e);unsigned d=stm3_cobs_decode(encoded.data(),e,decoded.data(),decoded.size());assert(d==n&&std::equal(a.begin(),a.end(),decoded.begin()));}
 std::printf("HOST ASan/UBSan PASS: %u independent int64 row controls,160 jobs,%u malformed packages,cancel/deadline/slice-overrun,60000 framing bytes,268 COBS lengths\n",checked,invalid);
}
