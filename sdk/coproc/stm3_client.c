#include "stm3_client.h"
#include <string.h>
uint32_t stm3_get32(const void*p){const uint8_t*s=p;return (uint32_t)s[0]|(uint32_t)s[1]<<8|(uint32_t)s[2]<<16|(uint32_t)s[3]<<24;}
void stm3_put32(void*p,uint32_t v){uint8_t*s=p;for(unsigned i=0;i<4;++i)s[i]=(uint8_t)(v>>(8*i));}
static uint32_t crc(const uint8_t*p,unsigned n){uint32_t v=~0u;while(n--){v^=*p++;for(unsigned i=0;i<8;++i)v=(v>>1)^(0xedb88320u&(0u-(v&1)));}return ~v;}
static unsigned encode(const uint8_t*in,unsigned n,uint8_t*out){
 unsigned at=1,code_at=0;uint8_t code=1;
 for(unsigned i=0;i<n;++i){
  if(!in[i]){out[code_at]=code;code_at=at++;code=1;}
  else{out[at++]=in[i];if(++code==255){out[code_at]=code;code_at=at++;code=1;}}
 }
 out[code_at]=code;return at;
}
static unsigned decode(uint8_t*p,unsigned n){
 unsigned at=0,i=0;
 while(i<n){unsigned code=p[i++];if(!code||code-1>n-i)return 0;
  for(unsigned j=1;j<code;++j){if(!p[i])return 0;p[at++]=p[i++];}
  if(code!=255&&i<n)p[at++]=0;
 }return at;
}
void stm3_client_init(stm3_client*c,const stm3_client_io*io){memset(c,0,sizeof(*c));c->io=*io;}
static int exchange(stm3_client*c,void*out,unsigned*used,uint32_t timeout,int send){
 const unsigned capacity=*used;*used=0;
 if(!c->tx_bytes||!timeout||timeout>1000000u)return S3_SIZE;
 const uint32_t start=c->io.micros(c->io.context);
 if(send){
  if(!c->io.send(c->io.context,c->tx,c->tx_bytes,timeout))return S3_IO;
  c->sent+=c->tx_bytes;++c->requests;
 }
 unsigned n=0;int overflow=0;
 for(;;){
  const uint32_t elapsed=c->io.micros(c->io.context)-start;
  if(elapsed>=timeout)return S3_TIMEOUT;
  int byte=c->io.read_byte(c->io.context,timeout-elapsed);
  if(byte<0)return byte==-1?S3_TIMEOUT:S3_IO;
  ++c->received;
  if(!byte){if(n||overflow)break;continue;}
  if(n<sizeof(c->rx))c->rx[n++]=(uint8_t)byte;else overflow=1;
 }
 c->last_us=c->io.micros(c->io.context)-start;
 if(c->last_us>c->max_us)c->max_us=c->last_us;
 if(overflow)return S3_FRAME;
 n=decode(c->rx,n);if(n<16)return S3_FRAME;
 const unsigned payload=(unsigned)c->rx[4]|(unsigned)c->rx[5]<<8;
 if(c->rx[0]!=S3_WIRE_VERSION||c->rx[1]!=(c->command|128u)||
    ((unsigned)c->rx[2]|(unsigned)c->rx[3]<<8)!=c->seq||c->rx[6]||c->rx[7]||
    payload<4||payload>256||n!=12+payload||stm3_get32(c->rx+n-4)!=crc(c->rx,n-4))return S3_FRAME;
 const uint32_t status=stm3_get32(c->rx+8);if(status)return status<=9?(int)status:S3_FRAME;
 if(payload-4>capacity||((payload-4)&&!out))return S3_SIZE;
 if(payload>4)memcpy(out,c->rx+12,payload-4);
 *used=payload-4;return 0;
}
static int prepare_request(stm3_client*c,uint8_t command,const void*in,unsigned bytes){
 if(bytes>256||(bytes&&!in)||!command||command&128u)return S3_SIZE;
 ++c->seq;c->command=command;
 uint8_t*p=c->rx;p[0]=S3_WIRE_VERSION;p[1]=command;p[2]=(uint8_t)c->seq;p[3]=(uint8_t)(c->seq>>8);
 p[4]=(uint8_t)bytes;p[5]=(uint8_t)(bytes>>8);p[6]=p[7]=0;
 if(bytes)memcpy(p+8,in,bytes);
 stm3_put32(p+8+bytes,crc(p,8+bytes));
 c->tx[0]=0;unsigned encoded=encode(p,12+bytes,c->tx+1);
 c->tx[encoded+1]=0;c->tx_bytes=encoded+2;
 return 0;
}
int stm3_client_request(stm3_client*c,uint8_t command,const void*in,unsigned bytes,void*out,unsigned*used,uint32_t timeout){
 if(!used)return S3_SIZE;
 int e=prepare_request(c,command,in,bytes);if(e)return e;
 return exchange(c,out,used,timeout,1);
}
int stm3_client_begin(stm3_client*c,uint8_t command,const void*in,unsigned bytes,uint32_t timeout){
 if(!timeout||timeout>1000000u)return S3_SIZE;
 int e=prepare_request(c,command,in,bytes);if(e)return e;
 if(!c->io.send(c->io.context,c->tx,c->tx_bytes,timeout))return S3_IO;
 c->sent+=c->tx_bytes;++c->requests;return 0;
}
int stm3_client_finish(stm3_client*c,void*out,unsigned*used,uint32_t timeout){
 if(!used)return S3_SIZE;
 return exchange(c,out,used,timeout,0);
}
int stm3_client_replay(stm3_client*c,void*out,unsigned*used,uint32_t timeout){
 if(!used)return S3_SIZE;
 return exchange(c,out,used,timeout,1);
}
