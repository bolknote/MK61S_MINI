/* Read-only model identity probe: bounded 4-KiB file API reads, SHA-256. */
#include <stdint.h>
#include <string.h>
#ifndef MK61_AI_SHA_HOST_ONLY
#include "mk61_app.h"
#endif
typedef struct { uint32_t h[8], count, used; uint8_t block[64]; } Sha;
static uint32_t rr(uint32_t x,unsigned n) { return (x>>n)|(x<<(32-n)); }
static void transform(Sha* s,const uint8_t* p) {
    static const uint32_t k[64]={
      0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
    uint32_t w[64];
    for(unsigned i=0;i<16;++i) w[i]=((uint32_t)p[4*i]<<24)|((uint32_t)p[4*i+1]<<16)|((uint32_t)p[4*i+2]<<8)|p[4*i+3];
    for(unsigned i=16;i<64;++i) w[i]=w[i-16]+(rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3))+w[i-7]+(rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10));
    uint32_t a=s->h[0],b=s->h[1],c=s->h[2],d=s->h[3],e=s->h[4],f=s->h[5],g=s->h[6],h=s->h[7];
    for(unsigned i=0;i<64;++i) {
      uint32_t t=h+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^((~e)&g))+k[i]+w[i];
      uint32_t u=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c));
      h=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;
    }
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void init(Sha* s) {
    const uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
    memset(s,0,sizeof(*s));memcpy(s->h,h,sizeof(h));
}
static void update(Sha* s,const uint8_t* data,uint32_t size) {
    s->count+=size;
    while(size) {
      uint32_t n=64-s->used;if(n>size)n=size;
      memcpy(s->block+s->used,data,n);s->used+=n;data+=n;size-=n;
      if(s->used==64) { transform(s,s->block);s->used=0; }
    }
}
static void finish(Sha* s,uint8_t out[32]) {
    const uint32_t bits=s->count<<3,high=s->count>>29;
    uint8_t last[128]={0x80};uint32_t pad=s->used<56?56-s->used:120-s->used;
    for(unsigned i=0;i<4;++i) { last[pad+i]=(uint8_t)(high>>(24-8*i));last[pad+4+i]=(uint8_t)(bits>>(24-8*i)); }
    update(s,last,pad+8);
    for(unsigned i=0;i<32;++i)out[i]=(uint8_t)(s->h[i/4]>>(24-8*(i%4)));
}
#ifdef MK61_AI_SHA_HOST_ONLY
void mk61_ai_sha256(const uint8_t* data,uint32_t size,uint32_t chunk,uint8_t out[32]) {
    Sha s;init(&s);if(!chunk)chunk=1;
    while(size) {uint32_t n=size<chunk?size:chunk;update(&s,data,n);data+=n;size-=n;}
    finish(&s,out);
}
#else
#ifndef MK61_AI_HASH_PATH
#define MK61_AI_HASH_PATH "/AI/MODEL.MKA"
#endif
#ifndef MK61_AI_HASH_BYTES
#define MK61_AI_HASH_BYTES 2093896U
#endif
int main(void) {
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_FORMAT);
    if(!s)return 1;
    mk61_service_file_info info={0};
    mk61_service_file_bytes r={MK61_AI_HASH_PATH,&info,0,sizeof(info)};
    if(!s->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_STAT,0,sizeof(r),&r)||info.directory||info.size!=MK61_AI_HASH_BYTES)return 2;
    static uint8_t bytes[4096];Sha hash;init(&hash);
    const uint32_t started=mk61_api->millis_ms();
    for(uint32_t at=0;at<info.size;) {
      uint32_t n=info.size-at;if(n>sizeof(bytes))n=sizeof(bytes);
      r.data=bytes;r.offset=at;r.size=n;
      if(!s->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_READ,0,sizeof(r),&r))return 3;
      update(&hash,bytes,n);at+=n;mk61_api->delay_ms(1);
    }
    uint8_t digest[32];char hex[65],line[160];finish(&hash,digest);
    const char digits[]="0123456789abcdef";
    for(unsigned i=0;i<32;++i) {hex[i*2]=digits[digest[i]>>4];hex[i*2+1]=digits[digest[i]&15];}hex[64]=0;
    const int n=mk61_app_snprintf(s,line,sizeof(line),"AI_MODEL_SHA bytes=%u sha256=%s ms=%u\r\n",info.size,hex,mk61_api->millis_ms()-started);
    s->call(MK61_SERVICE_DEBUG_WRITE,(uint32_t)n,0,0,line);
    return 0;
}
#endif
