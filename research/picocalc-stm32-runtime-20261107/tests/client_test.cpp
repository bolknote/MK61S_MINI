#include "stm3_client.h"
#include "stm3_runtime.h"
#include <cassert>
#include <cstring>
#include <cstdio>
static stm3_runtime server;
static uint32_t ticks;
static bool corrupt;
static uint32_t clock_us(void*){return ++ticks;}
static uint32_t address(void*,const void*){return 0x20003000;}
static int send(void*,const uint8_t*p,unsigned n,uint32_t){for(unsigned i=0;i<n;++i)stm3_feed(&server,p[i]);return 1;}
static int read(void*,uint32_t){uint8_t byte;if(stm3_transmit(&server,&byte,1)!=1)return -1;if(corrupt&&byte){corrupt=false;byte^=32;}return byte;}
int main(){
 const stm3_backend backend={nullptr,clock_us,address,nullptr,2250000,3};stm3_init(&server,&backend);
 const stm3_client_io io={nullptr,clock_us,send,read};stm3_client c;stm3_client_init(&c,&io);
 uint8_t out[256],in[257];unsigned n=sizeof(out);
 assert(!stm3_client_request(&c,S3_HELLO,nullptr,0,out,&n,100000)&&n==36);
 assert(stm3_get32(out)==1&&stm3_get32(out+28)==2250000);
 n=sizeof(out);assert(!stm3_client_replay(&c,out,&n,100000)&&n==36);
 assert(stm3_client_request(&c,S3_WRITE,in,257,out,&n,100000)==S3_SIZE);
 server.state=STM3_FINISHED;server.job_id=9;server.job.output_bytes=512;
 for(unsigned i=0;i<512;++i)server.output[i]=(uint8_t)(i*177u+31u);
 for(unsigned count=0;count<=252;++count){
  stm3_put32(in,9);stm3_put32(in+4,512-count);stm3_put32(in+8,count);n=sizeof(out);
  assert(!stm3_client_request(&c,S3_READ,in,12,out,&n,100000)&&n==count);
  assert(!memcmp(out,server.output+512-count,count));
 }
 n=sizeof(out);corrupt=true;assert(stm3_client_request(&c,S3_HELLO,nullptr,0,out,&n,100000)==S3_FRAME);
 n=sizeof(out);assert(!stm3_client_replay(&c,out,&n,100000));
 stm3_put32(in,10);stm3_put32(in+4,0);stm3_put32(in+8,1);n=sizeof(out);
 assert(stm3_client_request(&c,S3_READ,in,12,out,&n,100000)==STM3_E_JOB&&n==0);
 std::printf("CLIENT ASan/UBSan PASS: HELLO/replay,253 READ sizes,CRC rejection/replay,size/remote errors; bytes=%u/%u\n",c.sent,c.received);
}
