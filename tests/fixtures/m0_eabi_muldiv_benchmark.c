// Independent operand streams for binary64 multiplication and division.
#include "mk61_app.h"
#include <stdint.h>
typedef double Binary(double,double);
typedef union {double d;uint64_t u;} Bits;
#if M0_BENCH_QFPLIB
extern double qfp_dmul(double,double),qfp_ddiv(double,double);
static Binary* const functions[]={qfp_dmul,qfp_ddiv};
#elif !M0_BENCH_RESIDENT
extern double __aeabi_dmul(double,double),__aeabi_ddiv(double,double);
static Binary* const functions[]={__aeabi_dmul,__aeabi_ddiv};
#endif
enum {CASES=32,GROUPS=12,SAMPLES=1024,ROUNDS=9};
typedef struct {uint64_t a,b,result;} Pair;
static struct {
 uint32_t magic,version,cases,samples,rounds,groups;
 struct {Pair pairs[CASES];uint32_t raw[ROUNDS],control[ROUNDS];} rows[GROUPS];
} output;
static volatile uint64_t sink;
static uint32_t state=0x4D443040;
static uint32_t random32(void) {state^=state<<13;state^=state>>17;state^=state<<5;return state;}
static uint64_t fraction(void) {return ((uint64_t)(random32()&0xFFFFF)<<32)|random32();}
// Closest 32 quotients to a normal rounding midpoint among 131072 pairs
// from Python Random(0xD1D6140), two getrandbits(52) per pair. Ranked using
// exact integer remainders: |2*r-b|/b, r=(a<<(52+(a<b)))%b.
// Their distances are 0.0000026..0.0000748 ULP; neither operand is special.
static const struct {uint64_t a,b;} near_quotients[]={
 {UINT64_C(0x9FB4E9C96AA5D),UINT64_C(0xB118D3963556B)},
 {UINT64_C(0xFB23584A100BD),UINT64_C(0x3FB5CAD79DF38)},
 {UINT64_C(0x191F1504CE224),UINT64_C(0x7B2E517026E48)},
 {UINT64_C(0x684DCCA2E0912),UINT64_C(0xCED33D890F9C2)},
 {UINT64_C(0x2BA1157343A62),UINT64_C(0xCC113FA69A456)},
 {UINT64_C(0x3A85AA8CFA7CB),UINT64_C(0x9E51783256FCF)},
 {UINT64_C(0x2CAD66A14E5F5),UINT64_C(0x0B7EC0EDA214A)},
 {UINT64_C(0xE0D4AD1BAF238),UINT64_C(0xA86047A844B19)},
 {UINT64_C(0xE28B71EEC449D),UINT64_C(0xFB4D9322BB225)},
 {UINT64_C(0xB79E7B1C367D7),UINT64_C(0xFBC5A2CB2D54A)},
 {UINT64_C(0x0C7C088D8D640),UINT64_C(0xB1CCC864FE2AA)},
 {UINT64_C(0x7EF6D20F42FDF),UINT64_C(0xDE727905CF16E)},
 {UINT64_C(0x640D0826D8C1E),UINT64_C(0xA7D19A260C1FA)},
 {UINT64_C(0xF0FD5E073B092),UINT64_C(0xAAC1372D96D13)},
 {UINT64_C(0x2AE8EB6E1253A),UINT64_C(0x37BAF70DFB26B)},
 {UINT64_C(0xF03D4318241B0),UINT64_C(0xED18026E32D55)},
 {UINT64_C(0x6639A89C11A47),UINT64_C(0xADBA81A6EB8EE)},
 {UINT64_C(0x9C9409DEE85A5),UINT64_C(0x9B9BF1C17187E)},
 {UINT64_C(0x39FD247E127AB),UINT64_C(0x45AA6DA6C2687)},
 {UINT64_C(0x94492E8597087),UINT64_C(0x4E42E1E9CB06E)},
 {UINT64_C(0x7DE4C0B828B94),UINT64_C(0x9E1A04FD89A82)},
 {UINT64_C(0x85CEA409EC2A5),UINT64_C(0x84D1F8AAF2B8F)},
 {UINT64_C(0x41DC0C9E26E45),UINT64_C(0xAE5EE242ECC46)},
 {UINT64_C(0x8F70CABBD409B),UINT64_C(0x8ABBE58C848BE)},
 {UINT64_C(0x608A0C45D38BE),UINT64_C(0xB719959477C39)},
 {UINT64_C(0x3690293EF8AF7),UINT64_C(0x75AB6ED8A2E65)},
 {UINT64_C(0x110048FA43FD8),UINT64_C(0x82FD778B2EA7E)},
 {UINT64_C(0x1136DF06D788B),UINT64_C(0xAF30AD25366B9)},
 {UINT64_C(0xC8AE713333D16),UINT64_C(0xDB852C4EEA956)},
 {UINT64_C(0xA322B23E7A4C7),UINT64_C(0x3BF69E072CABF)},
 {UINT64_C(0x337A5959AA69F),UINT64_C(0xF84BC2ABC64F2)},
 {UINT64_C(0xD793AEC9F9A2D),UINT64_C(0x7B5F98A8C9E17)},
};
static __attribute__((noipa)) double identity(double a,double b) {(void)b;return a;}
static uint32_t micros(void) {__asm__ volatile("":::"memory");return *(volatile uint32_t*)0x40054028;}
static uint32_t time_function(Binary* f,const Pair* pairs) {
 const uint32_t begin=micros();
 for(unsigned i=0;i<SAMPLES;++i) {
  Bits a,b,r;a.u=pairs[i&(CASES-1)].a;b.u=pairs[i&(CASES-1)].b;
  r.d=f(a.d,b.d);sink=r.u;
 }
 return micros()-begin;
}
int main(void) {
 const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
 if(!s || !s->runtime)return MK61_APP_RUNTIME_ERROR;
 mk61_service_file marker={0};
 if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
      (uint32_t)(uintptr_t)M0_BENCH_MARKER,&marker)!=0)return MK61_APP_IO_ERROR;
 output.magic=0x30414C55;output.version=4;output.cases=CASES;
 output.samples=SAMPLES;output.rounds=ROUNDS;output.groups=GROUPS;
 for(unsigned group=0;group<GROUPS;++group) {
  unsigned op=group/6,kind=group%6;
#if M0_BENCH_RESIDENT
  Binary* f=(Binary*)s->runtime[op+2];
#else
  Binary* f=functions[op];
#endif
  for(unsigned i=0;i<CASES;++i) {
   unsigned ea=991+(random32()&63),eb=991+(random32()&63);
   uint64_t af=fraction(),bf=fraction();
   if(kind==1)bf&=UINT64_C(0xFFFFF00000000);
   if(kind==2) {af&=UINT64_C(0xFFFFF00000000);bf&=UINT64_C(0xFFFFF00000000);}
   if(kind==3)bf=op?(uint64_t)(i&7)<<49:0;
   if(kind==4) {
    if(op) {af=near_quotients[i].a;bf=near_quotients[i].b;}
    else {af=1+2*(i&7);bf=UINT64_C(1)<<51;if(i&8)af|=UINT64_C(1)<<50;}
   }
   if(kind==5) {
    if(op) {
     // Every normal exponent, with a quotient inside the fast guard.
     ea=1+random32()%2046;
     unsigned low=ea>1022?ea-1022:1,high=ea+1021<2046?ea+1021:2046;
     eb=low+random32()%(high-low+1);
    } else {
     unsigned sum=1024+random32()%2044;
     unsigned low=sum>2046?sum-2046:1,high=sum-1<2046?sum-1:2046;
     ea=low+random32()%(high-low+1);eb=sum-ea;
    }
   }
   Pair* p=&output.rows[group].pairs[i];
   p->a=((uint64_t)(i&1)<<63)|((uint64_t)ea<<52)|af;
   p->b=((uint64_t)((i>>1)&1)<<63)|((uint64_t)eb<<52)|bf;
   // Exercise both multiplication operand orders in the short paths.
   if(!op && (i&2)) {uint64_t swap=p->a;p->a=p->b;p->b=swap;}
   Bits a,b,r;a.u=p->a;b.u=p->b;r.d=f(a.d,b.d);p->result=r.u;
  }
  for(unsigned round=0;round<ROUNDS;++round) {
   mk61_api->service();output.rows[group].control[round]=time_function(identity,output.rows[group].pairs);
   mk61_api->service();output.rows[group].raw[round]=time_function(f,output.rows[group].pairs);
  }
 }
 mk61_service_write file={M0_BENCH_OUTPUT,(const uint8_t*)&output,sizeof(output),MK61_SERVICE_INVALID_ID};
 return s->call(MK61_SERVICE_FILE_WRITE,marker.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&file)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
