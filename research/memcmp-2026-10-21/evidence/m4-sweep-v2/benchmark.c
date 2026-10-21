/* Physical CPU measurements; source buffers stay unchanged between rounds.
 * The loop count depends on the compared prefix, including early mismatches. */
#include "mk61_app.h"
#include "baseline-memory.h"
#define FUNCTIONS 8U
#define ROUNDS 7U
#define ROWS 12U
#define LIMIT 4096U
typedef int (*Compare)(const void*,const void*,size_t);
extern int own4(const void*,const void*,size_t),own16(const void*,const void*,size_t),own64(const void*,const void*,size_t);
extern int memcmp(const void*,const void*,size_t),runtime_compare(const void*,const void*,size_t);
extern int control_compare(const void*,const void*,size_t);
#if !__ARM_ARCH_6M__
extern int own_low64(const void*,const void*,size_t);
#endif
const mk61_service_runtime_function* bench_runtime;
#ifdef BENCH_SELECTED_RUNTIME
extern int runtime_selected(const void*,const void*,size_t);
extern const mk61_service_runtime_function* mk61_app_runtime;
const mk61_service_runtime_function* bench_selected_runtime;
static mk61_service_runtime_function selected_runtime[MK61_RUNTIME_COUNT];
#ifndef BENCH_SELECTED_BODY
#define BENCH_SELECTED_BODY own64
#endif
#endif
static uint8_t left_buffer[LIMIT+80] __attribute__((aligned(16)));
static uint8_t right_buffer[LIMIT+80] __attribute__((aligned(16)));
static volatile int sink;
__attribute__((noipa)) int baseline(const void* a,const void* b,size_t n) { return mk61_memory_compare(a,b,n); }
__attribute__((noipa)) int byte_compare(const void* a,const void* b,size_t n) {
    const uint8_t *left=a,*right=b;
    for(size_t i=0;i<n;++i) if(left[i]!=right[i]) return (int)left[i]-right[i];
    return 0;
}
#if __ARM_ARCH_6M__
#define FLASH_SOURCE 0x10001000u
#define WARMUP 200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory"); return *(volatile uint32_t*)0x40054028u; }
#else
#define FLASH_SOURCE 0x08002000u
#define WARMUP 19200000u
static uint32_t tick(void) { __asm__ volatile("":::"memory"); return *(volatile uint32_t*)0xE0001004u; }
#endif
#ifdef BENCH_FLASH_HEADER
#include BENCH_FLASH_HEADER
#endif
/* mode: equal, first, byte 4, middle, last, identical pointers.
 * source: RAM/RAM, Flash/RAM, RAM/Flash. */
typedef struct { uint32_t size,left_offset,right_offset,loops,source,mode; } Input;
typedef struct { Input input;uint32_t control[ROUNDS],time[FUNCTIONS][ROUNDS]; } Row;
static struct { uint32_t h[64];Row rows[ROWS]; } report;
_Static_assert(sizeof(report)<=4096,"Bounded result file");
_Static_assert(MK61_RUNTIME_SLOT_memcmp==25,"Assembly runtime slot");
static const uint8_t* left(Input c) {
    return (c.source==1?(const uint8_t*)FLASH_SOURCE:left_buffer+32)+c.left_offset;
}
static const uint8_t* right(Input c) {
    return c.mode==5?left(c):(c.source==2?(const uint8_t*)FLASH_SOURCE:right_buffer+32)+c.right_offset;
}
static unsigned mismatch(Input c) {
    if(!c.size || !c.mode || c.mode==5) return c.size;
    return c.mode==1?0:c.mode==2?(c.size>4?4:c.size-1):c.mode==3?c.size/2:c.size-1;
}
static uint8_t pattern(unsigned i) { return (uint8_t)(i*13+(i>>8)*7); }
static uint8_t wanted(Input c,unsigned which,unsigned j) {
    unsigned offset=32+(which?c.right_offset:c.left_offset);
    uint8_t value=pattern(j)^(which?0xA5:0x3C);
    if(j>=offset && j-offset<c.size && (c.source==0 || (which?c.source==1:c.source==2))) {
        unsigned i=j-offset;
        value=c.source?((const uint8_t*)FLASH_SOURCE)[(which?c.left_offset:c.right_offset)+i]:pattern(i);
        if(which==(c.source!=2) && i==mismatch(c)) value^=0x80;
    }
    return value;
}
static void prepare(Input c) {
    for(unsigned j=0;j<c.size+64;++j) {
        left_buffer[j]=wanted(c,0,j);
        right_buffer[j]=wanted(c,1,j);
    }
}
static __attribute__((noipa)) uint32_t measure(Compare fn,Input c) {
    const uint8_t *a=left(c),*b=right(c);
    uint32_t begin=tick();
    for(unsigned i=0;i<c.loops;++i) sink=fn(a,b,c.size);
    return tick()-begin;
}
static int check(Compare fn,unsigned index,Input c) {
    prepare(c);
    int expected=byte_compare(left(c),right(c),c.size);
    int actual=fn(left(c),right(c),c.size);
    int good=((actual>0)-(actual<0))==((expected>0)-(expected<0));
    for(unsigned j=0;j<c.size+64;++j)
        if(left_buffer[j]!=wanted(c,0,j) || right_buffer[j]!=wanted(c,1,j)) good=0;
    ++report.h[5];
    if(!good) {
        ++report.h[6];report.h[7]=index;report.h[8]=c.size;report.h[9]=c.left_offset;
        report.h[10]=c.right_offset;report.h[28]=c.source;report.h[29]=c.mode;
        report.h[30]=(uint32_t)expected;report.h[31]=(uint32_t)actual;
    }
    if(c.size>=512 || !(report.h[5]&31)) mk61_api->service();
    return good;
}
static uint32_t read_byte_at(uintptr_t address) {
    uint32_t value;
    __asm__ volatile("ldrb %0,[%1]":"=l"(value):"l"(address):"memory");
    return value;
}
static uint32_t crc(const void* data,unsigned n) {
    uint32_t c=~0u;
    for(unsigned i=0;i<n;++i) { c^=read_byte_at((uintptr_t)data+i);for(unsigned b=0;b<8;++b)c=(c>>1)^(0xEDB88320u&(0u-(c&1u))); }
    return ~c;
}
int main(void) {
    for(unsigned i=0;i<64;++i) report.h[i]=0;
    const mk61_app_services* s=mk61_app_get_services(mk61_api,MK61_SERVICE_CAP_FILES|MK61_SERVICE_CAP_RUNTIME);
    if(!s || !s->runtime) return MK61_APP_RUNTIME_ERROR;
    mk61_service_file file={0};
    if(s->call(MK61_SERVICE_FILE_RESOLVE,MK61_SERVICE_ROOT_ID,MK61_SERVICE_FILE_MK61_BINARY,
        (uint32_t)(uintptr_t)(BENCH_ROOT "/INPUT.bin"),&file)) return MK61_APP_IO_ERROR;
    struct { uint32_t h[4];Input rows[ROWS]; } input;
    if(mk61_api->file_read(file.id,0,(uint8_t*)&input,sizeof(input))!=sizeof(input) ||
       input.h[0]!=0x4D434D50 || input.h[1]!=1 || !input.h[2] || input.h[2]>ROWS) return MK61_APP_INVALID_FILE;
    for(unsigned i=0;i<input.h[2];++i)
        if(input.rows[i].size>LIMIT || input.rows[i].left_offset>7 || input.rows[i].right_offset>7 ||
           input.rows[i].source>2 || input.rows[i].mode>5 || !input.rows[i].loops || input.rows[i].loops>65536)
            return MK61_APP_INVALID_FILE;
    bench_runtime=s->runtime;
#if __ARM_ARCH_6M__
    report.h[11]=read_byte_at(0x13u);
    if(report.h[11]!=3) return MK61_APP_RUNTIME_ERROR;
    report.h[15]=125000000;
    report.h[24]=crc((const void*)0,16384);
    if(report.h[24]!=0x0A428502u) return MK61_APP_RUNTIME_ERROR;
#else
    report.h[24]=crc((const void*)0x1FFF0000,0x7800);
    if(report.h[24]!=0x9F8F7DEDu) return MK61_APP_RUNTIME_ERROR;
    uint32_t demcr=*(volatile uint32_t*)0xE000EDFCu,dwt=*(volatile uint32_t*)0xE0001000u;
    *(volatile uint32_t*)0xE000EDFCu=demcr|0x1000000u;
    *(volatile uint32_t*)0xE0001000u=dwt|1u;
    report.h[11]=*(volatile uint32_t*)0x40023C00u;
    report.h[15]=96000000;
#endif
    report.h[13]=(uintptr_t)s->runtime[25];
    Compare functions[FUNCTIONS]={baseline,(Compare)s->runtime[25],runtime_compare,own4,own16,own64,memcmp,byte_compare};
#if !__ARM_ARCH_6M__
    functions[7]=own_low64;
#endif
#ifdef BENCH_FLASH_HEADER
    report.h[25]=crc((const void*)PAYLOAD_BASE,PAYLOAD_BYTES);
    if(report.h[25]!=PAYLOAD_CRC) goto finished;
    functions[0]=(Compare)FLASH_BASELINE;functions[3]=(Compare)FLASH_OWN4;
    functions[4]=(Compare)FLASH_OWN16;functions[5]=(Compare)FLASH_OWN64;
    functions[7]=(Compare)FLASH_LOW64;
#ifndef BENCH_SELECTED_RUNTIME
    functions[6]=(Compare)FLASH_SDK;
#endif
#endif
#ifdef BENCH_SELECTED_RUNTIME
    for(unsigned i=0;i<MK61_RUNTIME_COUNT;++i) selected_runtime[i]=s->runtime[i];
#ifdef BENCH_FLASH_HEADER
    selected_runtime[25]=(mk61_service_runtime_function)FLASH_SDK;
#else
    selected_runtime[25]=(mk61_service_runtime_function)BENCH_SELECTED_BODY;
#endif
    bench_selected_runtime=selected_runtime;
    mk61_app_runtime=selected_runtime;
    functions[4]=runtime_selected;
    functions[5]=(Compare)selected_runtime[25];
    report.h[26]=1;report.h[27]=(uintptr_t)selected_runtime[25];
#endif
    report.h[0]=0x4D435250;report.h[1]=2;report.h[2]=FUNCTIONS;report.h[3]=input.h[2];report.h[4]=ROUNDS;
    for(unsigned f=0;f<FUNCTIONS;++f) report.h[16+f]=(uintptr_t)functions[f];
    for(unsigned i=0;i<64;++i) ((uint8_t*)&report.h[32])[i]=((const uint8_t*)((uintptr_t)s->runtime[25]&~1u))[i];
    for(unsigned f=0;f<FUNCTIONS;++f) {
        if(functions[f](NULL,NULL,0)!=0) { ++report.h[6];report.h[7]=f; }
        ++report.h[5];
        if(input.h[3]) {
            for(unsigned n=0;n<=65;++n) for(unsigned a=0;a<4;++a) for(unsigned b=0;b<4;++b)
                for(unsigned mode=0;mode<5;++mode)
                    if(!check(functions[f],f,(Input){n,a,b,1,0,mode})) goto finished;
            const unsigned sizes[]={127,128,129,255,256,257,511,512,513,1024,4096};
            for(unsigned n=0;n<sizeof(sizes)/sizeof(sizes[0]);++n) for(unsigned a=0;a<4;++a)
                for(unsigned b=0;b<4;++b) for(unsigned source=0;source<3;++source)
                    for(unsigned mode=0;mode<=5;++mode)
                        if(!check(functions[f],f,(Input){sizes[n],a,b,1,source,mode})) goto finished;
        }
        for(unsigned c=0;c<input.h[2];++c) if(!check(functions[f],f,input.rows[c])) goto finished;
    }
    Input warm={1024,0,0,1,0,0};prepare(warm);
    uint32_t begin=tick();
    do {
        for(unsigned f=0;f<FUNCTIONS;++f) sink=functions[f](left(warm),right(warm),warm.size);
        mk61_api->service();
    } while((report.h[14]=tick()-begin)<WARMUP);
    for(unsigned c=0;c<input.h[2];++c) {
        Input row=input.rows[c];report.rows[c].input=row;prepare(row);
        for(unsigned r=0;r<ROUNDS;++r) {
            mk61_api->service();report.rows[c].control[r]=measure(control_compare,row);
            for(unsigned order=0;order<FUNCTIONS;++order) {
                unsigned f=(order+r+c)%FUNCTIONS;
                mk61_api->service();report.rows[c].time[f][r]=measure(functions[f],row);
            }
        }
    }
finished:;
#if !__ARM_ARCH_6M__
    *(volatile uint32_t*)0xE0001000u=dwt;
    *(volatile uint32_t*)0xE000EDFCu=demcr;
#endif
    mk61_service_write out={"RESULT",(const uint8_t*)&report,(uint32_t)(256+input.h[2]*sizeof(Row)),MK61_SERVICE_INVALID_ID};
    return s->call(MK61_SERVICE_FILE_WRITE,file.parent,MK61_SERVICE_INVALID_ID,MK61_SERVICE_FILE_MK61_BINARY,&out)?MK61_APP_OK:MK61_APP_IO_ERROR;
}
