/* Complete finite M0 libc workload. Transport, lease and Flash installation
 * belong to the external operator. No reset, IRQ/clock/cache writes or RTC. */
#include "mk61_app.h"
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include "binding.h"
extern size_t strnlen(const char*,size_t);
#ifndef MB_CODE_FLASH
#define MB_CODE_FLASH 0
#endif
#if !defined(__ARM_ARCH_6M__)
#error "RP2040 Cortex-M0+ only"
#endif
enum { ROWS=210, PAGE_ROWS=14, PAGES=15, PAGE_BYTES=4096, HEADER_BYTES=1024,
       REPORT_BYTES=HEADER_BYTES+PAGES*PAGE_BYTES, ROUNDS=7, TARGETS=9 };
enum { E_INPUT=1,E_CONTEXT,E_ANCHOR,E_GUARD,E_TIMER,E_RETURN,E_OUTPUT,E_REPLAY };
typedef struct {uint32_t flags,n,ao,bo,lengths,acrc,bcrc,expected;} mb_key;
typedef struct {uint32_t index,repeats,address,raw[TARGETS][ROUNDS];} mb_row;
typedef struct {uint32_t h[16];mb_row rows[PAGE_ROWS];uint8_t padding[336];} mb_page;
_Static_assert(sizeof(mb_key)==32 && sizeof(mb_row)==264 && sizeof(mb_page)==4096,"fixed wire");
_Static_assert(REPORT_BYTES==62464 && MK61_RUNTIME_COUNT==26,"bounded report, real runtime");
static uint32_t header[256];
static mb_page page;
static uint8_t source_a[1024] __attribute__((aligned(16)));
static uint8_t source_b[1024] __attribute__((aligned(16)));
static uint8_t destination[1024] __attribute__((aligned(16)));
static uint8_t arena[1552] __attribute__((aligned(16)));
static const mk61_app_services* services;
static mb_key key;
static const uint8_t *a,*b;
static uint8_t* d;
static unsigned op,aa,ba,banks,seed,alen,blen;
static uintptr_t targets[TARGETS];
static uint32_t last_job=UINT32_MAX,last_route=UINT32_MAX;
static volatile uint32_t* reg(uint32_t p){return (volatile uint32_t*)(uintptr_t)p;}
static uint32_t byte(const void* p,unsigned i){
  uint32_t v;uintptr_t at=(uintptr_t)p+i;
  __asm__ volatile("ldrb %0,[%1]":"=l"(v):"l"(at):"memory");return v;
}
static uint32_t crc_update(uint32_t v,const void* p,unsigned n){
  for(unsigned i=0;i<n;++i){v^=byte(p,i);for(unsigned bit=0;bit<8;++bit)v=(v>>1)^(0xedb88320u&(0u-(v&1u)));}return v;
}
static uint32_t crc(const void* p,unsigned n){return ~crc_update(UINT32_MAX,p,n);}
static uint32_t tick(void){
  __asm__ volatile("":::"memory");uint32_t t=*reg(0x40054028u);__asm__ volatile("":::"memory");return t;
}
static void context(uint32_t* out){
  out[0]=*reg(0xe000ed00u);
  __asm__ volatile("mrs %0,ipsr":"=r"(out[1]));
  __asm__ volatile("mrs %0,primask":"=r"(out[2]));
  __asm__ volatile("mrs %0,control":"=r"(out[3]));
  out[4]=*reg(0x14000000u);out[5]=*reg(0xe000e100u);
}
static int same_context(void){
  uint32_t now[6];context(now);
  for(unsigned i=0;i<6;++i)if(now[i]!=header[24+i])return 0;
  return (*reg(0x40008030u)&3u)==2u && *reg(0x40008034u)==0x100u &&
      *reg(0x40008038u)==4u && (*reg(0x4005802cu)&0x7ffu)==0x60cu;
}
static void fault(unsigned reason,unsigned detail,unsigned index,unsigned target){
  if(header[2] && header[2]!=UINT32_MAX)return;
  header[2]=reason;header[3]=detail;header[40]=index;header[41]=target;
}
static int anchors(void){
  if((uintptr_t)services->runtime!=MB_RUNTIME)return 0;
  const mk61_service_runtime_function* runtime=services->runtime;
  /* Do not fold a fixed resident address minus a relocated local table into
   * an out-of-image ABS32 addend; ordinary APP fixups must stay in the APP. */
  __asm__ volatile("":"+r"(runtime));
  for(unsigned i=0;i<26;++i)if((uintptr_t)runtime[i]!=mb_runtime[i])return 0;
  for(unsigned i=0;i<40;++i)if(byte((void*)(uintptr_t)MB_FOOTER,i)!=mb_footer[i])return 0;
  for(unsigned i=0;i<8;++i){
    unsigned observed=crc((void*)(uintptr_t)(mb_native_entry[i]&~1u),mb_native_bytes[i]);
    header[200+i]=observed;if(observed!=mb_native_crc32[i])return 0;
  }
  return 1;
}
static int prefill(void* opaque,uint32_t offset,uint8_t* output,uint32_t n){
  (void)opaque;
  if(offset>REPORT_BYTES || n>REPORT_BYTES-offset)return 0;
  /* The source callback is immutable, repeatable and order-independent.
   * Measurements run later, outside the callback and outside file writes. */
  for(uint32_t i=0;i<n;++i)output[i]=0xa5;
  return 1;
}
static int write_range(unsigned offset,void* data,unsigned n){
  mk61_service_file_bytes r={MB_NAMESPACE "/RESULT.bin",data,offset,n};
  return services->call(MK61_SERVICE_FILE_BYTES,MK61_FILE_BYTES_WRITE,0,sizeof(r),&r)!=0;
}
static int write_header(void){
  context(&header[30]);header[255]=0;header[255]=crc(header,sizeof(header));
  return write_range(0,header,sizeof(header));
}
static void clear_page(unsigned number,unsigned first){
  uint32_t* w=(uint32_t*)&page;for(unsigned i=0;i<1024;++i)w[i]=0;
  page.h[0]=0x3850474du;page.h[1]=1;page.h[2]=header[4];page.h[3]=header[5];
  page.h[4]=number;page.h[5]=first;page.h[9]=MB_TOKEN_A;page.h[10]=MB_TOKEN_B;
}
static int flush_page(unsigned number){
  page.h[7]=header[2]==UINT32_MAX?0:header[2];page.h[8]=header[40];
  page.h[15]=0;page.h[15]=crc(&page,sizeof(page));
  if(!write_range(HEADER_BYTES+number*PAGE_BYTES,&page,sizeof(page)))return 0;
  header[47]=number+1;return write_header();
}
static unsigned pattern(unsigned i){return 1u+(128u+37u*i)%255u;}
static unsigned destination_bytes(void){
  if(op==5u)return alen+1u;
  if(op==6u)return key.n?key.n:1u;
  if(op==7u)return seed+(key.n<alen?key.n:alen)+1u;
  return seed+1u;
}
static void reset_destination(void){
  /* Thirty-two canary bytes surround the entire declared output object.
   * The separate exhaustive semantic run checks every data-write envelope. */
  for(unsigned i=0;i<64u+ba+destination_bytes();++i)destination[i]=0xa5;
  d=destination+32+ba;
  for(unsigned i=0;i<seed;++i)d[i]=(uint8_t)pattern(i);
  d[seed]=0;
}
static int prepare_key(void){
  op=key.flags&7u;banks=(key.flags>>3)&3u;aa=(key.flags>>5)&3u;ba=(key.flags>>7)&3u;
  unsigned si=(key.flags>>9)&3u;if(si>2u || (key.flags&0xf800u))return 0;
  seed=si==2u?31u:si==1u?7u:0u;alen=key.lengths&65535u;blen=key.lengths>>16;
  if(alen>730u || blen>730u || (op==6u && key.n>736u) || key.ao<16u || key.bo<16u ||
     key.ao+alen+17u>MB_FIXTURE_BYTES || key.bo+blen+17u>MB_FIXTURE_BYTES ||
     key.ao%4u!=aa || key.bo%4u!=ba || !(key.flags>>16) || (key.flags>>16)>4096u)return 0;
  const uint8_t* fa=(const uint8_t*)(uintptr_t)(MB_FIXTURE_BASE+key.ao);
  const uint8_t* fb=(const uint8_t*)(uintptr_t)(MB_FIXTURE_BASE+key.bo);
  if(crc(fa,alen+1u)!=key.acrc || crc(fb,blen+1u)!=key.bcrc || fa[alen] || fb[blen])return 0;
  for(unsigned i=0;i<sizeof(source_a);++i)source_a[i]=source_b[i]=0xa5;
  for(unsigned i=0;i<=alen;++i)source_a[32+aa+i]=(uint8_t)byte(fa,i);
  for(unsigned i=0;i<=blen;++i)source_b[32+ba+i]=(uint8_t)byte(fb,i);
  a=(banks&2u)?fa:source_a+32+aa;b=(banks&1u)?fb:source_b+32+ba;
  reset_destination();return 1;
}
static int unchanged(int output){
  const uint8_t* fa=(const uint8_t*)(uintptr_t)(MB_FIXTURE_BASE+key.ao);
  const uint8_t* fb=(const uint8_t*)(uintptr_t)(MB_FIXTURE_BASE+key.bo);
  for(unsigned i=0;i<16;++i)if(byte(fa-16,i)!=0xa5 || byte(fa+alen+1,i)!=0xa5 ||
      byte(fb-16,i)!=0xa5 || byte(fb+blen+1,i)!=0xa5)return 0;
  unsigned input_frame=alen>blen?alen:blen;input_frame+=68u;
  for(unsigned i=0;i<input_frame;++i){
    unsigned wa=(i>=32+aa && i<=32+aa+alen)?byte(fa,i-32-aa):0xa5;
    unsigned wb=(i>=32+ba && i<=32+ba+blen)?byte(fb,i-32-ba):0xa5;
    if(source_a[i]!=wa || source_b[i]!=wb)return 0;
  }
  for(unsigned i=0;i<64u+ba+destination_bytes();++i){
    unsigned want=0xa5;
    if(i>=32+ba){
      unsigned pos=i-32-ba;
      if(pos<seed)want=pattern(pos);else if(pos==seed)want=0;
      if(output && op==5u && pos<=alen)want=byte(fa,pos);
      if(output && op==6u && pos<key.n)want=pos<alen?byte(fa,pos):0;
      if(output && op==7u && pos>=seed){
        unsigned n=key.n<alen?key.n:alen,at=pos-seed;
        if(at<n)want=byte(fa,at);else if(at==n)want=0;
      }
    }
    if(destination[i]!=want)return 0;
  }
  return 1;
}
static uintptr_t public_functions[8];
static int bind_targets(unsigned which){
  unsigned used=0;
  for(unsigned f=0;f<6;++f){
    const uint8_t* code=(void*)(uintptr_t)(MB_FIXTURE_BASE+mb_leaf_offset[which][f]);
    used=(used+15u)&~15u;
    uintptr_t start=((uintptr_t)arena+15u)&~(uintptr_t)15u;start+=used;
    if(used+mb_leaf_bytes[which][f]>1536u)return 0;
    if(!MB_CODE_FLASH)for(unsigned i=0;i<mb_leaf_bytes[which][f];++i)((uint8_t*)start)[i]=(uint8_t)byte(code,i);
    targets[f]=(MB_CODE_FLASH?(uintptr_t)code:start)|1u;
    used+=mb_leaf_bytes[which][f];
    unsigned observed=crc((void*)(targets[f]&~1u),mb_leaf_bytes[which][f]);
    header[144+which*6+f]=observed;
    if(observed!=mb_leaf_crc32[which][f])return 0;
  }
  __asm__ volatile("dsb\nisb":::"memory");
  targets[6]=public_functions[which];targets[7]=mb_native_entry[which];
  targets[8]=mb_slots[which]<0?0:(uintptr_t)services->runtime[(unsigned)mb_slots[which]];
  header[48+which]=targets[8]?0x1ffu:0xffu;
  for(unsigned f=0;f<TARGETS;++f)header[64+which*TARGETS+f]=(uint32_t)targets[f];
  return 1;
}
static int timer_qualification(void){
  uint32_t wall=mk61_api->millis_ms(),begin=tick(),elapsed=0,us=0;
  for(unsigned i=0;i<1000000u;++i){elapsed=mk61_api->millis_ms()-wall;us=tick()-begin;if(elapsed>=8u)break;}
  header[16]=elapsed;header[17]=us;
  return elapsed>=8u && elapsed<=250u && us>0u && us<0x80000000u &&
      us+2000u>=1000u*elapsed && us<=1000u*elapsed+2000u;
}
__attribute__((noipa)) static int measure(mb_row* row,unsigned target){
  typedef unsigned (*length_fn)(const char*);
  typedef unsigned (*bounded_length_fn)(const char*,size_t);
  typedef int (*compare_fn)(const void*,const void*);
  typedef int (*bounded_compare_fn)(const void*,const void*,size_t);
  typedef char* (*copy_fn)(char*,const char*);
  typedef char* (*bounded_copy_fn)(char*,const char*,size_t);
  const uintptr_t address=targets[target];
  const unsigned repeats=row->repeats;uint32_t value=0;
  for(unsigned round=0;round<ROUNDS;++round){
    reset_destination();
    if(!same_context() || !unchanged(0)){fault(E_CONTEXT,3,row->index,target);return 0;}
    /* One checked primer establishes the same warm entry context for each
     * target. The measured loop retains call/return checks and no subtraction. */
    for(unsigned pass=0;pass<2;++pass){
      unsigned limit=pass?repeats:1u,at=0;uint32_t start=tick();int okay=1;
#define LOOP(expr,wanted) do { for(at=0;at<limit;++at){value=(uint32_t)(uintptr_t)(expr);__asm__ volatile("":::"memory");if(value!=(uint32_t)(uintptr_t)(wanted)){okay=0;break;}} }while(0)
      switch(op){
      case 0: LOOP(((length_fn)address)((const char*)a),key.expected);break;
      case 1:
      case 2:
      case 3:
        for(at=0;at<limit;++at){
          int v=op==1u?((compare_fn)address)(a,b):((bounded_compare_fn)address)(a,b,key.n);
          value=(uint32_t)((v>0)-(v<0));__asm__ volatile("":::"memory");
          if(value!=key.expected){okay=0;break;}
        }break;
      case 4: LOOP(((bounded_length_fn)address)((const char*)a,key.n),key.expected);break;
      case 5: LOOP(((copy_fn)address)((char*)d,(const char*)a),d);break;
      case 6: LOOP(((bounded_copy_fn)address)((char*)d,(const char*)a,key.n),d);break;
      default:
        for(at=0;at<limit;++at){
          d[seed]=0;value=(uint32_t)(uintptr_t)((bounded_copy_fn)address)((char*)d,(const char*)a,key.n);
          __asm__ volatile("":::"memory");if(value!=(uint32_t)(uintptr_t)d){okay=0;break;}
        }break;
      }
#undef LOOP
      uint32_t elapsed=tick()-start;
      if(pass)row->raw[target][round]=elapsed;
      if(!okay){header[42]=round;header[43]=at;header[44]=value;header[45]=op>=5u?(uintptr_t)d:key.expected;header[224]=pass;header[225]=elapsed;fault(E_RETURN,1,row->index,target);return 0;}
      if(!unchanged(1)){fault(E_GUARD,1,row->index,target);return 0;}
      if(!same_context()){fault(E_CONTEXT,4,row->index,target);return 0;}
      if(pass && (!elapsed || elapsed>=0x80000000u)){fault(E_TIMER,2,row->index,target);return 0;}
      reset_destination();
    }
  }
  return 1;
}
int main(void){
  if(!mk61_app_api_compatible(mk61_api,sizeof(*mk61_api),MK61_APP_CAP_TIME|MK61_APP_CAP_FILES))return MK61_APP_RUNTIME_ERROR;
  services=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME|MK61_SERVICE_CAP_FILE_BYTES|MK61_SERVICE_CAP_FILE_WRITE_SOURCE);
  if(!services || !services->runtime)return MK61_APP_RUNTIME_ERROR;
  for(unsigned i=0;i<256;++i)header[i]=0;
  header[0]=0x38484c4du;header[1]=1;header[2]=UINT32_MAX;header[9]=ROUNDS;header[10]=TARGETS;
  header[11]=MB_TOKEN_A;header[12]=MB_TOKEN_B;header[18]=1000000;header[19]=crc(mb_footer,40);
#ifdef MK61_APP_SHARED_RUNTIME
  header[20]=1;
#endif
  header[21]=MB_CODE_FLASH;header[22]=mk61_app_image_crc;
  context(&header[24]);
  header[36]=*reg(0x40008030u);header[37]=*reg(0x40008034u);
  header[38]=*reg(0x40008038u);header[39]=*reg(0x4005802cu)&0x7ffu;
  header[208]=(uintptr_t)source_a;header[209]=(uintptr_t)source_b;header[210]=(uintptr_t)destination;
  header[211]=((uintptr_t)arena+15u)&~15u;header[212]=(uintptr_t)header;header[213]=(uintptr_t)&page;
  header[214]=MB_FOOTER;header[215]=MB_RUNTIME;header[254]=REPORT_BYTES;
  public_functions[0]=(uintptr_t)strlen;public_functions[1]=(uintptr_t)strcmp;
  public_functions[2]=(uintptr_t)strncmp;public_functions[3]=(uintptr_t)memcmp;
  public_functions[4]=(uintptr_t)strnlen;public_functions[5]=(uintptr_t)strcpy;
  public_functions[6]=(uintptr_t)strncpy;public_functions[7]=(uintptr_t)strncat;
  mk61_service_file file={0};uint32_t input[16];
  if(services->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,(uint32_t)(uintptr_t)(MB_NAMESPACE "/INPUT.bin"),&file))return MK61_APP_IO_ERROR;
  mk61_service_write_source out={"RESULT",NULL,prefill,REPORT_BYTES,MK61_SERVICE_INVALID_ID};
  if(!services->call(MK61_SERVICE_FILE_WRITE_SOURCE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&out))return MK61_APP_IO_ERROR;
  header[46]=out.id;
  if(mk61_api->file_read(file.id,0,(uint8_t*)input,64)!=64){fault(E_INPUT,1,UINT32_MAX,UINT32_MAX);goto done;}
  header[4]=input[2];header[5]=input[3];header[6]=input[4];header[7]=input[5];
  if(input[0]!=0x38424c4du || input[1]!=1u || input[3]>3u ||
      input[6]!=MB_TOKEN_A || input[7]!=MB_TOKEN_B || crc(input,60)!=input[15] ||
      input[3]!=header[20]*2u+header[21] ||
      (input[2]==UINT32_MAX?(input[4] || input[5] || input[14]):
      (input[4]>=MB_CASES || input[4]%ROWS || input[2]!=input[4]/ROWS ||
       !input[5] || input[5]>ROWS || input[5]!=(MB_CASES-input[4]<ROWS?MB_CASES-input[4]:ROWS))) ||
      mk61_api->file_size(file.id)!=64u+input[5]*32u){fault(E_INPUT,2,UINT32_MAX,UINT32_MAX);goto done;}
  if(last_route==input[3] && last_job!=UINT32_MAX && (input[2]==UINT32_MAX || input[2]<=last_job)){fault(E_REPLAY,1,UINT32_MAX,UINT32_MAX);goto done;}
  last_route=input[3];last_job=input[2];
  if((header[24]&0xff00fff0u)!=0x4100c600u || header[25] || header[26] || header[27] || !same_context()){
    fault(E_CONTEXT,1,UINT32_MAX,UINT32_MAX);goto done;}
  if(input[2]!=UINT32_MAX)for(unsigned i=0;i<6;++i)if(input[8+i]!=header[24+i]){fault(E_CONTEXT,2,UINT32_MAX,UINT32_MAX);goto done;}
  if(!anchors()){fault(E_ANCHOR,1,UINT32_MAX,UINT32_MAX);goto done;}
  header[13]=crc((void*)(uintptr_t)MB_FIXTURE_BASE,MB_FIXTURE_BYTES);
  header[14]=crc(services->runtime,104);
  if(header[13]!=MB_FIXTURE_CRC){fault(E_ANCHOR,2,UINT32_MAX,UINT32_MAX);goto done;}
  for(unsigned i=0;i<8;++i)if(!bind_targets(i)){fault(E_ANCHOR,3,UINT32_MAX,i);goto done;}
  if(!timer_qualification()){fault(E_TIMER,1,UINT32_MAX,UINT32_MAX);goto done;}
  if(!write_header())return MK61_APP_IO_ERROR;
  unsigned active=UINT32_MAX;uint32_t key_crc=UINT32_MAX;
  for(unsigned row=0;row<input[5];++row){
    unsigned pn=row/PAGE_ROWS,slot=row%PAGE_ROWS,index=input[4]+row;
    if(!slot)clear_page(pn,index);
    page.h[6]=slot+1;
    if(mk61_api->file_read(file.id,64+row*32,(uint8_t*)&key,32)!=32){fault(E_INPUT,3,index,UINT32_MAX);goto page_fault;}
    key_crc=crc_update(key_crc,&key,32);
    if(!prepare_key()){fault(E_INPUT,4,index,UINT32_MAX);goto page_fault;}
    if(active!=op){if(!bind_targets(op)){fault(E_ANCHOR,4,index,UINT32_MAX);goto page_fault;}active=op;}
    mb_row* result=&page.rows[slot];result->index=index;result->repeats=key.flags>>16;result->address=(uintptr_t)a;
    for(unsigned order=0;order<TARGETS;++order){
      unsigned f=(order+index)%TARGETS;if(!targets[f])continue;
      mk61_api->service();if(!measure(result,f))goto page_fault;
    }
    ++header[8];
    if(slot==PAGE_ROWS-1u || row+1u==input[5])if(!flush_page(pn))return MK61_APP_IO_ERROR;
    continue;
page_fault:
    if(!flush_page(pn))return MK61_APP_IO_ERROR;
    goto done;
  }
  if(~key_crc!=input[14]){fault(E_INPUT,5,UINT32_MAX,UINT32_MAX);goto done;}
  header[23]=crc((void*)(uintptr_t)MB_FIXTURE_BASE,MB_FIXTURE_BYTES);
  if(header[23]!=MB_FIXTURE_CRC || !anchors())fault(E_ANCHOR,5,UINT32_MAX,UINT32_MAX);
done:
  if(header[2]==UINT32_MAX)header[2]=0;
  if(!write_header())return MK61_APP_IO_ERROR;
  return header[2]?MK61_APP_RUNTIME_ERROR:MK61_APP_OK;
}
