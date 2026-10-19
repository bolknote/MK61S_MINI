// Identical C operand generator for SRAM timing and ARM instruction profiling.
#include <stdint.h>
#ifndef M0_BENCH_FULL_STREAMS
#define M0_BENCH_FULL_STREAMS 0
#endif
#ifndef M0_BENCH_INPUTS_ONLY
#define M0_BENCH_INPUTS_ONLY 0
#endif
#define M0_BENCH_SEED (M0_BENCH_FULL_STREAMS?0xF0116140u:0x4D443040u)
typedef struct {uint64_t a,b,result;} Pair;
static uint32_t random32(uint32_t* state) {*state^=*state<<13;*state^=*state>>17;*state^=*state<<5;return *state;}
static uint64_t fraction(uint32_t* state) {
 // Specify the PRNG call order so profiling and APP builds share inputs.
 const uint32_t high=random32(state)&0xFFFFF;
 const uint32_t low=random32(state);
 return ((uint64_t)high<<32)|low;
}
#if M0_BENCH_FULL_STREAMS
// Closest 32 exact-ratio distances from a rounding midpoint among 131072
// pairs with odd 53-bit significands. Python Random seeds 0xF011D0B1
// (products) and 0xF011D1D8 (quotients); getrandbits(52)|1 per operand.
// Distances are ranked with exact rational arithmetic, without host floats.
static const struct {uint64_t a,b;} near_full_products[]={
 {UINT64_C(0xB453EAA6D9111),UINT64_C(0xA6A75BC04913F)},
 {UINT64_C(0x01E49344C24C7),UINT64_C(0x009E5F04FEF5F)},
 {UINT64_C(0x0C3A3C15A14DF),UINT64_C(0x92B7F5541549B)},
 {UINT64_C(0x65BFD2DCC84A1),UINT64_C(0xBF7DD70BA0F23)},
 {UINT64_C(0x600EA26D3EE57),UINT64_C(0xAAE394E30FA4F)},
 {UINT64_C(0x663A5FB4FCA17),UINT64_C(0x7C2096A2CC179)},
 {UINT64_C(0x2540981D39C1F),UINT64_C(0x56113300E8927)},
 {UINT64_C(0xA4F6371E90A81),UINT64_C(0x676990B700661)},
 {UINT64_C(0xCEE140D511783),UINT64_C(0xF25C05E6D5619)},
 {UINT64_C(0xF8ECE7BE7E655),UINT64_C(0x251ADDB0E7EC1)},
 {UINT64_C(0x81E25A141D209),UINT64_C(0x08CC5C799DB5B)},
 {UINT64_C(0xBEDFEEEB010A5),UINT64_C(0xF62E31C9F1A21)},
 {UINT64_C(0xC91FA83F368FD),UINT64_C(0xAEB59D882FAA7)},
 {UINT64_C(0x8D52B8975BC89),UINT64_C(0xA3AB35E005551)},
 {UINT64_C(0xA8ECD51921471),UINT64_C(0x3AF9A71D7CF33)},
 {UINT64_C(0xAAA371A7AD8B1),UINT64_C(0x111429B8D75F7)},
 {UINT64_C(0x2857478204155),UINT64_C(0xE87F5C0735369)},
 {UINT64_C(0xFCAD7B1C2608F),UINT64_C(0x82B62441A7BDF)},
 {UINT64_C(0x298D11BEFF0C3),UINT64_C(0x9A8FFD87FC751)},
 {UINT64_C(0x50E4FF7AD2F05),UINT64_C(0xC865BD27B0891)},
 {UINT64_C(0x917D991595959),UINT64_C(0x3E4693B1B4363)},
 {UINT64_C(0xFD1D11CA70C8F),UINT64_C(0x1ED6F70A1E907)},
 {UINT64_C(0xA71EA020F83EB),UINT64_C(0xA6DFB59FF78ED)},
 {UINT64_C(0x983DB931DEFAB),UINT64_C(0xBD6CF3BA5D6A5)},
 {UINT64_C(0xD9F65C3C431E1),UINT64_C(0xBD709338AEB37)},
 {UINT64_C(0xD4E3692A05B3F),UINT64_C(0x151BD8A1D23E9)},
 {UINT64_C(0x6E2C4BC390BFD),UINT64_C(0xEF207D5EE90E9)},
 {UINT64_C(0xC725E8994100F),UINT64_C(0xBAA9190152C07)},
 {UINT64_C(0x970816FABD44B),UINT64_C(0x093E8F60324F1)},
 {UINT64_C(0x46297794FC92F),UINT64_C(0xD571D443B929B)},
 {UINT64_C(0xCCA51A9B693AB),UINT64_C(0x2A0F0EA2ADEAB)},
 {UINT64_C(0xBFB03C962A1C7),UINT64_C(0xC90C416FA4E05)},
};
static const struct {uint64_t a,b;} near_full_quotients[]={
 {UINT64_C(0x1DE91E67928BB),UINT64_C(0x299D37A9F72AD)},
 {UINT64_C(0xEC2E2EEB2117D),UINT64_C(0xC95C0AE816357)},
 {UINT64_C(0x72ACA8C340ADB),UINT64_C(0x4CBDBBA86FCAF)},
 {UINT64_C(0xFDD456CB08CEF),UINT64_C(0x61E278939C939)},
 {UINT64_C(0xADFAE05D466FF),UINT64_C(0x989EEC466861F)},
 {UINT64_C(0xA120F328EA60F),UINT64_C(0x33CFD7866378D)},
 {UINT64_C(0x073C28BB48735),UINT64_C(0x1D7CC77336859)},
 {UINT64_C(0xA3B9573A6F2A1),UINT64_C(0x4311EB97407CF)},
 {UINT64_C(0x26C73F49A893B),UINT64_C(0x6370AD17C9867)},
 {UINT64_C(0x310DA68BF7563),UINT64_C(0x71D8A1E438E25)},
 {UINT64_C(0x93154553D5233),UINT64_C(0xDD88AB4D532C3)},
 {UINT64_C(0xCDA59500D9E75),UINT64_C(0x6005E30E20DC1)},
 {UINT64_C(0xE3447D580CF99),UINT64_C(0xFA728521834F7)},
 {UINT64_C(0xEBF1830D220C3),UINT64_C(0xD3533C2916D21)},
 {UINT64_C(0x68229B9E46E97),UINT64_C(0xBE524613E7303)},
 {UINT64_C(0xF080D3AB33691),UINT64_C(0xB41249E6BC639)},
 {UINT64_C(0x3CB7AD40A12E3),UINT64_C(0x4CD8CA0BA2F0D)},
 {UINT64_C(0xE03512C9B81CD),UINT64_C(0x11E33AF9DB1C5)},
 {UINT64_C(0x96AA215AE6CE7),UINT64_C(0xE10EBA85CEB7F)},
 {UINT64_C(0xEAE945E13AD69),UINT64_C(0xE6BDA68D4E91D)},
 {UINT64_C(0x537100E6EDF4B),UINT64_C(0x540C2E443E403)},
 {UINT64_C(0xE8149FD4C7E75),UINT64_C(0xA3C503A130FD3)},
 {UINT64_C(0x18CA9FC558A05),UINT64_C(0x30043D00026E1)},
 {UINT64_C(0xFCD3096D2D781),UINT64_C(0xCFD20CCB55369)},
 {UINT64_C(0x3913F969B0CE1),UINT64_C(0x7985DCF40E1C9)},
 {UINT64_C(0xD3F0832A399F7),UINT64_C(0x4C2282F349875)},
 {UINT64_C(0x08E5EE22F831B),UINT64_C(0x5AD162BE35FC1)},
 {UINT64_C(0x5C2AFBED8FEAB),UINT64_C(0x2F63BEB3E255F)},
 {UINT64_C(0x138B4B4C6ABD9),UINT64_C(0x68924F0296481)},
 {UINT64_C(0x8A7CBE3BEB7F7),UINT64_C(0x9296B0B2DC9C5)},
 {UINT64_C(0x9E488C7407C0F),UINT64_C(0xD2FC0F2F39879)},
 {UINT64_C(0xB3B342988B293),UINT64_C(0xBD7C25F95B711)},
};
#else
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
#endif

uint32_t m0_bench_seed(void) {return M0_BENCH_SEED;}
// selector = operation<<16 | stream<<8 | pair. State/output are supplied
// by the caller so the same generator also runs in a bounded ARM test stack.
void m0_bench_pair(uint32_t* state,unsigned selector,Pair* p) {
 unsigned op=selector>>16,kind=(selector>>8)&255,i=selector&255;
 unsigned ea=991+(random32(state)&63),eb=991+(random32(state)&63);
 uint64_t af=fraction(state),bf=fraction(state);
#if M0_BENCH_FULL_STREAMS
 af|=1;bf|=1; // Every significand needs all 53 significant bits.
 if(kind==1) {
  if(op) {if(af>bf) {uint64_t swap=af;af=bf;bf=swap;}}
  else {af&=(UINT64_C(1)<<50)-1;bf&=(UINT64_C(1)<<50)-1;}
 }
 if(kind==2) {
  if(op) {if(af<bf) {uint64_t swap=af;af=bf;bf=swap;}}
  else {af|=UINT64_C(1)<<51;bf|=UINT64_C(1)<<51;}
 }
 if(kind==3) {
  static const uint32_t low[]={1,3,0x80000001,0xFFFFFFFF};
  af=(af&UINT64_C(0xFFFFF00000000))|low[i&3];
  bf=(bf&UINT64_C(0xFFFFF00000000))|low[(i>>2)&3];
 }
 if(kind==4) {
  if(op) {
   ea=1+random32(state)%2046;
   unsigned low=ea>1022?ea-1022:1,high=ea+1021<2046?ea+1021:2046;
   eb=low+random32(state)%(high-low+1);
  } else {
   unsigned sum=1024+random32(state)%2044;
   unsigned low=sum>2046?sum-2046:1,high=sum-1<2046?sum-1:2046;
   ea=low+random32(state)%(high-low+1);eb=sum-ea;
  }
 }
 if(kind==5) {
  af=op?near_full_quotients[i].a:near_full_products[i].a;
  bf=op?near_full_quotients[i].b:near_full_products[i].b;
 }
#else
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
     ea=1+random32(state)%2046;
     unsigned low=ea>1022?ea-1022:1,high=ea+1021<2046?ea+1021:2046;
     eb=low+random32(state)%(high-low+1);
    } else {
     unsigned sum=1024+random32(state)%2044;
     unsigned low=sum>2046?sum-2046:1,high=sum-1<2046?sum-1:2046;
     ea=low+random32(state)%(high-low+1);eb=sum-ea;
    }
   }
#endif
 p->a=((uint64_t)(i&1)<<63)|((uint64_t)ea<<52)|af;
 p->b=((uint64_t)((i>>1)&1)<<63)|((uint64_t)eb<<52)|bf;
 if(!op && (i&2)) {uint64_t swap=p->a;p->a=p->b;p->b=swap;}
 p->result=0;
}

#if !M0_BENCH_INPUTS_ONLY
#include "mk61_app.h"
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
static struct {
 uint32_t magic,version,cases,samples,rounds,groups;
 struct {Pair pairs[CASES];uint32_t raw[ROUNDS],control[ROUNDS];} rows[GROUPS];
} output;
static volatile uint64_t sink;
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
 uint32_t state=m0_bench_seed();
 output.magic=0x30414C55;output.version=M0_BENCH_FULL_STREAMS?5:4;output.cases=CASES;
 output.samples=SAMPLES;output.rounds=ROUNDS;output.groups=GROUPS;
 for(unsigned group=0;group<GROUPS;++group) {
  unsigned op=group/6,kind=group%6;
#if M0_BENCH_RESIDENT
  Binary* f=(Binary*)s->runtime[op+2];
#else
  Binary* f=functions[op];
#endif
  for(unsigned i=0;i<CASES;++i) {
   Pair* p=&output.rows[group].pairs[i];
   m0_bench_pair(&state,(op<<16)|(kind<<8)|i,p);
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

#endif
